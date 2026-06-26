# Migração para PostgreSQL

Este projeto foi configurado para usar PostgreSQL por padrão.

## 1. Criar o ambiente Python

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

## 2. Instalar PostgreSQL no sistema

Em Ubuntu/Debian:

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl enable --now postgresql
```

## 3. Criar usuário e banco

```bash
sudo -u postgres psql
```

Dentro do prompt do PostgreSQL:

```sql
CREATE USER planejamento_pcc WITH PASSWORD 'planejamento_pcc';
CREATE DATABASE planejamento_pcc OWNER planejamento_pcc;
ALTER ROLE planejamento_pcc SET client_encoding TO 'utf8';
ALTER ROLE planejamento_pcc SET default_transaction_isolation TO 'read committed';
ALTER ROLE planejamento_pcc SET timezone TO 'America/Bahia';
\q
```

## 4. Configurar variáveis locais

```bash
cp .env.example .env
```

Edite o `.env` se quiser trocar nome do banco, usuário, senha, host ou porta.

## 5. Criar as tabelas no PostgreSQL

```bash
.venv/bin/python manage.py migrate
```

## 6. Criar usuário administrador

```bash
.venv/bin/python manage.py createsuperuser
```

## 7. Validar

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py runserver
```
