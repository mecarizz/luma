# Luma Trendyol Manager

Luma is a Windows desktop app for managing Trendyol sellers, monitoring orders,
generating thermal labels, and maintaining a product catalog.

## Run from source

Use Python 3.10 or newer:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python ui_main.py
```

Add seller credentials through the Seller Config tab. Credentials and operational
data are stored locally under `%LOCALAPPDATA%\Luma` in the packaged app. For
security, never commit `.env`, seller profiles, product/order data, or logs.

Use the **Product Catalog** tab to search and filter products, add or edit
catalog entries, and remove products. Catalog edits are saved locally with
automatic backups.

The desktop app starts monitoring enabled sellers automatically. Depending on
their settings, it may change cargo providers and print labels. For a safe
standalone watcher check, use:

```powershell
python trendyol_watcher.py --dry-run --once
```

For manual handling, open **Orders & Labels**, fetch packages for a seller (or
all sellers), select the packages, and choose **Print as TEX**, **Print as DHL**,
or a carrier from the custom selection. Luma switches the selected packages in
Trendyol and refreshes them before printing so the labels use the new carrier's
tracking barcodes. The automatic watcher pauses during these manual operations.

The application interface supports English and Turkish. Use the **Language**
menu to change languages; the selection is saved for the next launch.

## Build a Windows release

Install the build dependencies and run the build script:

```powershell
python -m pip install -r requirements-build.txt
.\build_windows.bat
```

The executable and release ZIP are created under `dist/`. The public release
workflow runs when a version tag is pushed:

```powershell
git tag v1.0.3
git push origin v1.0.3
```

The tag must use `vMAJOR.MINOR.PATCH`. GitHub Actions builds the EXE, publishes
the ZIP, and includes its SHA-256 checksum. In the packaged app, Luma checks for
updates shortly after startup and asks before downloading or installing one.
You can also choose **Help > Check for Updates** to check manually. Releases
are public, so only publish data that is intended to be public.

## Project layout

- `ui_*.py`, `app_controller.py`, `worker.py`: desktop app
- `trendyol_watcher.py`, `trendyol_labels.py`: watcher and label generation
- `core/`: shared configuration, seller, catalog, reporting, and update code
- `tests/`: offline tests; they do not call Trendyol or print
- `release_defaults/`: empty catalog and rules included in public builds
- `manage_products.py`, `reports.py`: companion command-line tools
- `.github/workflows/release.yml`: tagged Windows release workflow

Run tests with:

```powershell
python -m unittest discover -s tests -v
```
