# Midnight 00:01 · Music Sorter

A Windows app that sorts a big, messy music collection into a clean library. It **only copies**: your original files are never changed, moved or deleted, and every copy waits for your approval.

- Checks tags against MusicBrainz and, if you allow them, Deezer, Apple Music, Discogs, Spotify and Last.fm
- Review screens: Songs, Albums, Artists (list with photos and *Solo artist*), Quick mode, Library
- Finds duplicates, keeps a permanent log of every decision and every copy
- Plain Python + pywebview window, no account needed

Version **V2.0.6**

## Install (Windows 10/11)

1. Download this repository (**Code → Download ZIP**) or the setup zip from **Releases**, and unzip the whole folder.
2. Double-click **Install Midnight.bat** and answer Y / N.
   It can install Python 3.12 (only if missing), the helper libraries, ffmpeg (recommended) and shortcuts. It needs internet once.
3. Start the app from the **Midnight 00-01** shortcut.

The app is copied to `%LOCALAPPDATA%\Midnight 00-01\app`. Run **Uninstall Midnight.bat** to remove it; your music and libraries are not touched.

To run it without installing: open the `app` folder and double-click `Start Midnight App.bat`.

## Optional

`fpcalc.exe` ([Chromaprint](https://acoustid.org/chromaprint)) next to `midnight_app.py` lets the app identify songs by sound.

## Requirements

Windows, Python 3.10+ and: `mutagen openpyxl pillow pywebview unidecode`. The installer sets these up.

## Status

Personal project, tested mainly on one machine. The installer has not been tested on many systems yet. Please open an issue if something fails and paste the messages from the window.

## License

MIT, see [LICENSE](LICENSE).
