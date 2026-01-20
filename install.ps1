# Install script for CEDS-SHACL-Generator
# This script installs all required Python packages

Write-Host "Installing CEDS-SHACL-Generator dependencies..." -ForegroundColor Cyan

# Check if Python is installed
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Found $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "Python is not installed or not in PATH. Please install Python first." -ForegroundColor Red
    exit 1
}

# Upgrade pip first
Write-Host "`nUpgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install requirements
Write-Host "`nInstalling requirements from requirements.txt..." -ForegroundColor Yellow
python -m pip install -r requirements.txt

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nAll dependencies installed successfully!" -ForegroundColor Green
} else {
    Write-Host "`nSome packages failed to install. Please check the errors above." -ForegroundColor Red
    exit 1
}
