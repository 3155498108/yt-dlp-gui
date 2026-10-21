import datetime
import os
import platform
import re
import shutil
import stat
import sys
import zipfile
from typing import List, Tuple
import logging


import requests
from PySide6.QtCore import QThread, Signal

from utils import ROOT, BIN_DIR
import subprocess as sp

logger = logging.getLogger(__name__)

# The managed binaries have to take precedence over copies that are installed
# system wide. Otherwise a stale yt-dlp/ffmpeg/deno that is found first on
# PATH is used, which is a common cause of hard to diagnose download failures
# (see issue #77).
os.environ["PATH"] = os.pathsep.join(
    [str(BIN_DIR), str(ROOT / "bin"), os.environ.get("PATH", "")]
)

BINARIES = {
    "Linux": {
        "ffmpeg": "ffmpeg-linux64-v4.1",
        "ffprobe": "ffprobe-linux64-v4.1",
        "yt-dlp": "yt-dlp_linux",
        "deno": "deno-x86_64-unknown-linux-gnu.zip",
    },
    "Darwin": {
        "ffmpeg": "ffmpeg-osx64-v4.1",
        "ffprobe": "ffprobe-osx64-v4.1",
        "yt-dlp": "yt-dlp_macos",
        "deno": "deno-x86_64-apple-darwin.zip",
    },
    "Windows": {
        "ffmpeg": "ffmpeg-win64-v4.1.exe",
        "ffprobe": "ffprobe-win64-v4.1.exe",
        "yt-dlp": "yt-dlp.exe",
        "deno": "deno-x86_64-pc-windows-msvc.zip",
    },
}

YT_DLP_BASE_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
FFMPEG_BASE_URL = "https://github.com/imageio/imageio-binaries/raw/183aef992339cc5a463528c75dd298db15fd346f/ffmpeg/"
DENO_BASE_URL = "https://github.com/denoland/deno/releases/latest/download/"


class DepWorker(QThread):
    progress = Signal(str)

    def __init__(self, update_ytdlp: bool):
        super().__init__()
        self.missing: List[Tuple[str, str]] = []
        self.failed: List[str] = []
        self.update_ytdlp = update_ytdlp

    def _check_missing_dependencies(self):
        system_os = platform.system()
        if system_os not in BINARIES:
            return

        required_binaries = ["ffmpeg", "ffprobe", "yt-dlp", "deno"]
        missing_exes = [
            exe
            for exe in required_binaries
            if not shutil.which(exe)
            and not (
                BIN_DIR / (exe + (".exe" if system_os == "Windows" else ""))
            ).exists()
        ]

        if not missing_exes:
            return

        BIN_DIR.mkdir(parents=True, exist_ok=True)

        for exe in missing_exes:
            binary_name = BINARIES[system_os][exe]

            if exe == "yt-dlp":
                url = YT_DLP_BASE_URL + binary_name
            elif exe == "deno":
                url = DENO_BASE_URL + binary_name
            else:
                url = FFMPEG_BASE_URL + binary_name

            target_name = f"{exe}.exe" if system_os == "Windows" else exe
            target_path = str(BIN_DIR / target_name)

            self.missing.append((url, target_path))

    def chmod(self):
        try:
            st = os.stat(self.filename)
            os.chmod(self.filename, st.st_mode | stat.S_IEXEC)
        except OSError:
            pass

    def run(self):
        try:
            self._check_missing_dependencies()

            for url, filename in self.missing:
                self.url, self.filename = url, filename
                try:
                    self._download()
                    self.chmod()
                except Exception as e:
                    logger.error(
                        f"Failed to download dependency {filename}: {e}", exc_info=True
                    )
                    self.failed.append(os.path.basename(filename))
                    self.progress.emit(
                        f"Failed to download dependency: {os.path.basename(filename)}"
                    )

            if self.update_ytdlp:
                self.update()
        finally:
            # The download button stays disabled unless this signal is emitted,
            # so it has to be sent even when something went wrong.
            self.finished.emit()

    def update(self):
        """Update yt-dlp to the latest release.

        `yt-dlp -U` is not able to update a binary that was installed with pip
        or from a wheel (it exits with code 100) and it fails as well when the
        GitHub API is unreachable or rate limited. In those cases the latest
        release is downloaded directly, just like during the installation.
        """
        system_os = platform.system()
        if system_os not in BINARIES:
            return

        create_window = sp.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        output = ""
        updated = False
        returncode = 1

        try:
            with sp.Popen(
                ["yt-dlp", "-U"],
                stdout=sp.PIPE,
                stderr=sp.STDOUT,
                text=True,
                universal_newlines=True,
                creationflags=create_window,
            ) as p:
                for line in p.stdout:
                    output += line
                    if line.startswith("Updating to"):
                        updated = True
                        self.progress.emit("Updating yt-dlp...")

                returncode = p.returncode
        except OSError as e:
            logger.error(f"yt-dlp update failed: {e}")
            output = str(e)

        if returncode == 0 and updated:
            self.progress.emit("yt-dlp updated")
            logger.info(f"yt-dlp updated\n{output}")
            return

        logger.error(f"yt-dlp update failed returncode: {returncode}\n{output}")

        installed = self._installed_version()

        if installed and (datetime.date.today() - installed).days < 30:
            # The installed version is recent enough, a temporarily unreachable
            # update server must not cause a download on every startup.
            self.progress.emit("yt-dlp is up to date")
            return

        # Fall back to downloading the latest release directly.
        self.progress.emit("Updating yt-dlp...")

        try:
            target_name = "yt-dlp.exe" if system_os == "Windows" else "yt-dlp"
            self.url = YT_DLP_BASE_URL + BINARIES[system_os]["yt-dlp"]
            self.filename = str(BIN_DIR / target_name)
            self._download()
            self.chmod()
        except Exception as e:
            logger.error(f"yt-dlp update failed: {e}", exc_info=True)
            self.progress.emit("yt-dlp update failed")
            return

        self.progress.emit("yt-dlp updated")
        logger.info("yt-dlp updated by downloading the latest release")

    def _installed_version(self):
        """Return the release date of the yt-dlp that is going to be used."""
        create_window = sp.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        try:
            out = sp.check_output(
                ["yt-dlp", "--version"],
                stderr=sp.STDOUT,
                text=True,
                creationflags=create_window,
            )
        except (OSError, sp.SubprocessError):
            return None

        match = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", out)

        if not match:
            return None

        try:
            return datetime.date(
                int(match.group(1)), int(match.group(2)), int(match.group(3))
            )
        except ValueError:
            return None

    def _download(self):
        response = requests.get(self.url, stream=True, timeout=(10, 60))
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))
        block_size = 8192
        downloaded = 0

        display_name = os.path.basename(self.filename)
        temp_filename = self.filename + ".part"

        with open(temp_filename, "wb") as f:
            for chunk in response.iter_content(chunk_size=block_size):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)

                if total_size > 0:
                    percentage = int((downloaded / total_size) * 100)
                    dl_mb = downloaded / (1024 * 1024)
                    tot_mb = total_size / (1024 * 1024)
                    status = f"Downloading dependency: ({display_name}) {dl_mb:.2f} / {tot_mb:.2f} MB {percentage}%"
                else:
                    percentage = 0
                    dl_mb = downloaded / (1024 * 1024)
                    status = f"{display_name}: {dl_mb:.2f} MB"

                self.progress.emit(status)

        if downloaded == 0:
            raise OSError(f"Downloaded file is empty: {self.url}")

        if self.url.endswith(".zip"):
            zip_filename = temp_filename + ".zip"
            shutil.move(temp_filename, zip_filename)

            try:
                self._extract_zip(zip_filename, display_name)
            finally:
                if os.path.exists(zip_filename):
                    os.remove(zip_filename)
            return

        if os.path.exists(self.filename):
            os.remove(self.filename)
        os.rename(temp_filename, self.filename)

    def _extract_zip(self, zip_filename, target_name):
        """Extract the executable from a downloaded archive.

        The layout of the archive is not guaranteed: the executable can be
        located at the root or inside a directory and the first entry is not
        necessarily the file that is needed.
        """
        with zipfile.ZipFile(zip_filename, "r") as zf:
            entries = [i for i in zf.infolist() if not i.is_dir()]

            if not entries:
                raise OSError(f"No files found in archive: {zip_filename}")

            entry = next(
                (
                    i
                    for i in entries
                    if os.path.basename(i.filename) == target_name
                ),
                entries[0],
            )

            with zf.open(entry) as source, open(self.filename, "wb") as target:
                shutil.copyfileobj(source, target)

        logger.info(f"Extracted {entry.filename} from {zip_filename}")
