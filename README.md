# Login Tester

A high-performance, asynchronous desktop application for automating login tests. Built with Python 3.12, Playwright, and Tkinter.

## Features

- **Concurrent Testing**: Uses an async worker pool to test multiple accounts simultaneously.
- **Memory Efficient**: Streams credentials from disk, supporting files with millions of lines without loading them entirely into memory.
- **Configurable Detection**: Define success and failure based on URL patterns, page titles, DOM selectors, or text content.
- **Checkpoint & Resume**: Automatically saves state. If you close the app or it crashes, you can resume exactly where you left off.
- **Modern Dark UI**: Clean, responsive Tkinter interface with real-time statistics and log streaming.
- **Result Categorization**: Automatically writes results to specific files (success, failure, error, etc.) immediately.

## Setup & Running

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Run the application:**
   ```bash
   python app.py
   ```

## Building Executable

To package the application into a standalone desktop application with the browser binaries bundled inside:

### For Linux / macOS:
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install Playwright Chromium browser locally in the virtual environment / python package folder
PLAYWRIGHT_BROWSERS_PATH=0 playwright install chromium

# 3. Build the desktop app
pyinstaller --onedir --windowed --clean app.py
```

### For Windows:
* **CMD**:
  ```cmd
  rem 1. Install dependencies
  pip install -r requirements.txt

  rem 2. Install Playwright Chromium browser locally in the virtual environment / python package folder
  set PLAYWRIGHT_BROWSERS_PATH=0
  playwright install chromium

  rem 3. Build the desktop app
  pyinstaller --onedir --windowed --clean app.py
  ```
* **PowerShell**:
  ```powershell
  # 1. Install dependencies
  pip install -r requirements.txt

  # 2. Install Playwright Chromium browser locally in the virtual environment / python package folder
  $env:PLAYWRIGHT_BROWSERS_PATH="0"
  playwright install chromium

  # 3. Build the desktop app
  pyinstaller --onedir --windowed --clean app.py
  ```

The standalone application will be generated in the `dist/app/` directory. You can run the executable from there without needing external browser installations.

## Configuration

Configuration is managed via the GUI or by editing `config/config.yaml`.
You must point the application to a text file containing `username:password` credentials (one per line).

> **WARNING**: This tool is designed strictly for testing web applications that you own or have explicit authorization to test. Unauthorized access attempts are illegal.
