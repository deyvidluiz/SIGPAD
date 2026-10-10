# SIGPAD

Aplicação Django para planejamento e acompanhamento de atividades docentes.
Reúne turmas, disciplinas, conteúdos programáticos, avaliações, notas, frequência,
alertas e relatórios em PDF.

## Requisitos

- Python 3.12, 3.13 ou 3.14, compatíveis com o Django 6.0 utilizado pelo projeto
  ([compatibilidade oficial](https://docs.djangoproject.com/en/6.0/faq/install/#what-python-version-can-i-use-with-django)).
- PostgreSQL em execução, com um banco e um usuário destinados ao ambiente local.
- Dependências Python listadas em [requirements.txt](requirements.txt).

## Executar localmente

Os comandos abaixo devem ser executados na raiz do repositório, em Linux/macOS.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

No Windows, ative o ambiente com `.venv\Scripts\activate` no Prompt de Comando.

Se ainda não tiver configurado o PostgreSQL, siga as etapas de instalação e
criação do banco em [POSTGRES_SETUP.md](POSTGRES_SETUP.md).

Na primeira configuração, copie `.env.example` para `.env` e ajuste os valores
para o seu banco local. Preserve o `.env` caso ele já exista.

| Variáveis | Finalidade |
| --- | --- |
| `DJANGO_SECRET_KEY` | Chave da aplicação; use uma chave própria. |
| `DJANGO_DEBUG` | Modo de desenvolvimento (`True` no ambiente local). |
| `DJANGO_ALLOWED_HOSTS` | Hosts separados por vírgula, como `localhost,127.0.0.1`. |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Nome do banco e credenciais locais. |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Endereço e porta do PostgreSQL. |
| `POSTGRES_CONN_MAX_AGE`, `POSTGRES_CONNECT_TIMEOUT` | Tempos de conexão, em segundos. |

O projeto carrega `.env` automaticamente. Variáveis já definidas no processo têm
precedência sobre o arquivo. O `.env` está no `.gitignore` e não deve ser publicado.

Com o banco local configurado:

```bash
python manage.py check
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Acesse <http://127.0.0.1:8000/login/> para entrar no sistema ou
<http://127.0.0.1:8000/admin/> para acessar a administração.

As migrações já estão versionadas; `makemigrations` só é necessário ao alterar
os modelos. A configuração atual usa PostgreSQL: o arquivo `db.sqlite3` presente
no repositório não é utilizado por ela. `migrate` cria/aplica o esquema no banco
configurado, mas não transfere dados do SQLite para o PostgreSQL.

## Estrutura

| Caminho | Conteúdo |
| --- | --- |
| `planejamento/` | Modelos, formulários, views, rotas e migrações do sistema. |
| `planejamento_pcc/` | Configurações Django e pontos de entrada ASGI/WSGI. |
| `templates/` | Páginas renderizadas pelo Django. |
| `static/` | CSS, JavaScript e imagens da interface. |
| `media/` | Arquivos enviados pelos usuários. |
| `POSTGRES_SETUP.md` | Configuração local do PostgreSQL. |

## Verificações durante o desenvolvimento

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
```

O primeiro comando verifica a configuração da aplicação; o segundo identifica
alterações nos modelos ainda não representadas nas migrações, sem criar arquivos.
Essas verificações não substituem testes dos fluxos de cadastro, notas e frequência.

Para validar instalação e migrações, use um banco local separado, com dados de
teste. O servidor `runserver` é destinado ao desenvolvimento.
