#!/usr/bin/env bash
# Build do SIGPAD no Render: dependencias, arquivos estaticos e migracoes.
# Nao apaga dados: "migrate" apenas aplica migracoes pendentes.
set -o errexit
set -o pipefail
set -o nounset

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python manage.py collectstatic --noinput
python manage.py migrate --noinput
