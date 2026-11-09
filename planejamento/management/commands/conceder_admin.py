"""
Concede o papel de administrador do SIGPAD (/painel/) a UM usuario existente.

    python manage.py conceder_admin <usuario>              # mostra o diagnostico e pede confirmacao
    python manage.py conceder_admin <usuario> --verificar  # somente leitura, nao altera nada
    python manage.py conceder_admin <e-mail> --email       # localiza a conta pelo e-mail

O que o comando faz:
  * adiciona o usuario ao grupo "Administradores SIGPAD" (criado pela migracao 0024);
O que o comando NAO faz:
  * nao cria usuarios, nao ativa contas, nao altera senha;
  * nao marca is_superuser nem is_staff;
  * nao altera nenhuma outra conta.

Usa o banco configurado no settings (DATABASE_URL tem prioridade), entao pode
ser executado localmente apontando para o PostgreSQL do Render.
"""

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Q

from planejamento.permissoes import GRUPO_ADMIN, is_admin_sigpad

MIGRACAO_GRUPO = ('planejamento', '0024_grupo_administradores_sigpad')


class Command(BaseCommand):
    help = 'Adiciona um usuario existente ao grupo "Administradores SIGPAD" (acesso ao /painel/).'

    def add_arguments(self, parser):
        parser.add_argument('identificador', help='Nome de usuario (ou e-mail, com --email) da conta existente.')
        parser.add_argument('--email', action='store_true', help='Interpreta o identificador como e-mail.')
        parser.add_argument('--verificar', action='store_true', help='Apenas mostra o diagnostico, sem alterar nada.')
        parser.add_argument('--sim', action='store_true', help='Confirma a alteracao sem pergunta interativa.')

    def handle(self, *args, identificador, email, verificar, sim, **opcoes):
        self._mostrar_banco()
        self._verificar_migracao()

        usuario = self._localizar(identificador.strip(), email)
        self._mostrar_usuario(usuario)

        if is_admin_sigpad(usuario):
            self.stdout.write(self.style.SUCCESS('\nEsta conta JA tem acesso ao /painel/. Nada foi alterado.'))
            return
        if not usuario.is_active:
            raise CommandError(
                'A conta esta INATIVA. Este comando nao reativa contas; reative-a conscientemente antes '
                '(por exemplo, pelo /admin/) e rode o comando de novo.'
            )
        if verificar:
            self.stdout.write(self.style.WARNING('\n--verificar: nenhuma alteracao feita. A conta ainda NAO acessa o /painel/.'))
            return

        if not sim:
            resposta = input(
                f'\nAdicionar "{usuario.username}" ao grupo "{GRUPO_ADMIN}" neste banco?\n'
                f'Digite o nome de usuario ({usuario.username}) para confirmar: '
            ).strip()
            if resposta != usuario.username:
                raise CommandError('Confirmacao nao confere. Nada foi alterado.')

        with transaction.atomic():
            grupo = Group.objects.get(name=GRUPO_ADMIN)
            usuario.groups.add(grupo)

        usuario = User.objects.get(pk=usuario.pk)  # recarrega sem cache
        if not is_admin_sigpad(usuario):
            raise CommandError('Falha inesperada: a conta continua sem acesso administrativo.')
        self.stdout.write(self.style.SUCCESS(
            f'\nPronto: "{usuario.username}" agora e administrador do SIGPAD. '
            'Saia e entre novamente no site e acesse /painel/.'
        ))

    # ------------------------------------------------------------------
    def _mostrar_banco(self):
        banco = settings.DATABASES['default']
        origem = 'DATABASE_URL' if getattr(settings, 'DATABASE_URL', None) else 'variaveis POSTGRES_* / local'
        self.stdout.write('Banco conectado (sem credenciais):')
        self.stdout.write(f'  origem da configuracao: {origem}')
        self.stdout.write(f"  host: {banco.get('HOST') or '(local)'}  porta: {banco.get('PORT') or '-'}")
        self.stdout.write(f"  banco: {banco.get('NAME')}  engine: {connection.vendor}")
        self.stdout.write(f'  usuarios cadastrados: {User.objects.count()}')

    def _verificar_migracao(self):
        aplicada = MigrationRecorder(connection).migration_qs.filter(
            app=MIGRACAO_GRUPO[0], name=MIGRACAO_GRUPO[1],
        ).exists()
        self.stdout.write(f"  migracao {MIGRACAO_GRUPO[1]}: {'aplicada' if aplicada else 'NAO aplicada'}")
        if not aplicada or not Group.objects.filter(name=GRUPO_ADMIN).exists():
            raise CommandError(
                'O grupo de administradores nao existe neste banco (migracao 0024 pendente). '
                'Confira se o deploy mais recente terminou e se este e o banco correto; '
                'depois rode "python manage.py migrate".'
            )

    def _localizar(self, identificador, por_email):
        if not identificador:
            raise CommandError('Informe o nome de usuario ou e-mail.')
        if por_email:
            encontrados = list(User.objects.filter(email__iexact=identificador)[:2])
            if len(encontrados) > 1:
                raise CommandError('Mais de uma conta usa este e-mail. Informe o nome de usuario.')
        else:
            encontrados = list(User.objects.filter(username=identificador)[:1])
        if encontrados:
            return encontrados[0]

        parecidos = User.objects.filter(
            Q(username__icontains=identificador) | Q(email__icontains=identificador.split('@')[0])
        ).values_list('username', flat=True)[:5]
        dica = f' Contas com nome parecido: {", ".join(parecidos)}.' if parecidos else ''
        raise CommandError(
            f'Usuario "{identificador}" nao encontrado neste banco.{dica} '
            'O comando nao cria contas: cadastre-se primeiro no site.'
        )

    def _mostrar_usuario(self, usuario):
        grupos = ', '.join(usuario.groups.values_list('name', flat=True)) or '(nenhum)'
        self.stdout.write(f'\nConta: {usuario.username} ({usuario.get_full_name() or "sem nome"})')
        self.stdout.write(f'  is_active: {usuario.is_active}  is_staff: {usuario.is_staff}  is_superuser: {usuario.is_superuser}')
        self.stdout.write(f'  grupos: {grupos}')
        self.stdout.write(f'  acesso ao /painel/: {"SIM" if is_admin_sigpad(usuario) else "NAO"}')
