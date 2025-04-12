# Set working directory
$projectPath = "C:\Users\lucas\OneDrive\Desktop\gptveo"
Set-Location $projectPath

Write-Host "Cleaning up project at: $projectPath"

# Create .streamlit if missing
if (-not (Test-Path ".streamlit")) {
    New-Item -ItemType Directory -Path ".streamlit" | Out-Null
    Write-Host "Created .streamlit folder"
}

# Move secrets.toml to .streamlit
if (Test-Path "secrets.toml") {
    Move-Item -Force "secrets.toml" ".streamlit\secrets.toml"
    Write-Host "Moved secrets.toml to .streamlit/"
}

# Remove redundant or unused files
$toDelete = @("app.py", "test.py")
foreach ($file in $toDelete) {
    if (Test-Path $file) {
        Remove-Item -Force $file
        Write-Host "Removed $file"
    }
}

# Create or update .gitignore
$gitignorePath = ".gitignore"
$gitignoreRules = @"
# Ignore compiled files and cache
__pycache__/
*.py[cod]

# Ignore secrets and config
.streamlit/secrets.toml

# Ignore video outputs
*.mp4

# Ignore editor configs
.vscode/
.DS_Store
Thumbs.db
"@

if (Test-Path $gitignorePath) {
    Add-Content $gitignorePath "`n$gitignoreRules"
    Write-Host ".gitignore updated"
} else {
    $gitignoreRules | Out-File -Encoding UTF8 $gitignorePath
    Write-Host ".gitignore created"
}

Write-Host "`nProject cleanup complete."
