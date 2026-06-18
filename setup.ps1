# setup.ps1
# Configura o ambiente virtual Python local e instala as dependências

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Inicializando Setup do Data Mesh & Lakehouse..." -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Criação do Ambiente Virtual
if (Test-Path -Path ".venv") {
    Write-Host "[1/3] Ambiente virtual .venv já existe." -ForegroundColor Yellow
} else {
    Write-Host "[1/3] Criando ambiente virtual (.venv)..." -ForegroundColor Green
    python -m venv .venv
}

# 2. Ativação e Upgrade do pip
Write-Host "[2/3] Ativando .venv e atualizando pip..." -ForegroundColor Green
& .venv\Scripts\activate.ps1
python -m pip install --upgrade pip

# 3. Instalação das Dependências
Write-Host "[3/3] Instalando dependências de requirements.txt..." -ForegroundColor Green
pip install -r requirements.txt

# 4. Verificação de Sucesso
if ($LASTEXITCODE -eq 0) {
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host "Setup concluído com sucesso!" -ForegroundColor Green
    Write-Host "Para ativar o ambiente virtual no PowerShell:" -ForegroundColor Green
    Write-Host "  .venv\Scripts\activate.ps1" -ForegroundColor Yellow
    Write-Host "==================================================" -ForegroundColor Green
} else {
    Write-Host "==================================================" -ForegroundColor Red
    Write-Host "Erro durante a instalação das dependências." -ForegroundColor Red
    Write-Host "==================================================" -ForegroundColor Red
}
