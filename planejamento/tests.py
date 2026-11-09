from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Aluno, Aula, Disciplina, NotaAluno, Presenca, ProcessoAvaliativo, Turma
from .permissoes import GRUPO_ADMIN, is_admin_sigpad

SENHA = 'SenhaForte!2026'


@override_settings(SECURE_SSL_REDIRECT=False)
class BasePainelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.grupo = Group.objects.get_or_create(name=GRUPO_ADMIN)[0]
        cls.admin = User.objects.create_user('coord', 'coord@escola.test', SENHA, first_name='Coord')
        cls.admin.groups.add(cls.grupo)
        cls.root = User.objects.create_superuser('root', 'root@escola.test', SENHA)
        cls.prof = User.objects.create_user('prof', 'prof@escola.test', SENHA, first_name='Ana')
        cls.prof2 = User.objects.create_user('prof2', 'prof2@escola.test', SENHA, first_name='Bruno')

        cls.turma = Turma.objects.create(professor=cls.prof, nome='6º Ano A', ano_letivo=2026, turno='MATUTINO')
        cls.disciplina = Disciplina.objects.create(
            turma=cls.turma, professor=cls.prof, nome='Matemática', carga_horaria=10,
            quantidade_aulas=10, ano_escolar='6º ano',
        )
        cls.aluno1 = Aluno.objects.create(turma=cls.turma, nome='Aluno Um', matricula='1')
        cls.aluno2 = Aluno.objects.create(turma=cls.turma, nome='Aluno Dois', matricula='2')
        aulas = [
            Aula.objects.create(turma=cls.turma, disciplina=cls.disciplina, data=date(2026, 3, dia), quantidade_aulas=1,
                                conteudo_aplicado='Conteudo')
            for dia in (2, 3, 4, 5)
        ]
        Presenca.objects.create(aula=aulas[0], aluno=cls.aluno2, presente=False)
        Presenca.objects.create(aula=aulas[1], aluno=cls.aluno2, presente=False)
        prova = ProcessoAvaliativo.objects.create(
            turma=cls.turma, disciplina=cls.disciplina, titulo='Prova', tipo='Prova', valor_maximo=Decimal('10'),
            periodo='1_BIMESTRE', status='CORRIGIDA',
        )
        # avaliacao futura sem notas nao deve derrubar a media parcial
        ProcessoAvaliativo.objects.create(
            turma=cls.turma, disciplina=cls.disciplina, titulo='Trabalho futuro', tipo='Trabalho',
            valor_maximo=Decimal('10'), periodo='2_BIMESTRE', data_abertura=date(2099, 1, 1),
            data_fechamento=date(2099, 1, 2),
        )
        NotaAluno.objects.create(aluno=cls.aluno1, processo=prova, nota=Decimal('8'))
        NotaAluno.objects.create(aluno=cls.aluno2, processo=prova, nota=Decimal('4'))

    def entrar(self, usuario):
        self.client.force_login(usuario)


class PermissoesPainelTests(BasePainelTestCase):
    def urls_painel(self):
        return [
            reverse('painel_dashboard'),
            reverse('painel_usuarios'),
            reverse('painel_usuario_criar'),
            reverse('painel_usuario_detalhes', args=[self.prof.id]),
            reverse('painel_usuario_editar', args=[self.prof.id]),
            reverse('painel_usuario_senha', args=[self.prof.id]),
            reverse('painel_turmas'),
            reverse('painel_turma_criar'),
            reverse('painel_turma_detalhes', args=[self.turma.id]),
            reverse('painel_turma_editar', args=[self.turma.id]),
            reverse('painel_disciplinas'),
            reverse('painel_disciplina_criar'),
            reverse('painel_disciplina_editar', args=[self.disciplina.id]),
            reverse('painel_planejamento'),
            reverse('painel_planejamento') + '?aba=conteudos',
            reverse('painel_relatorios'),
        ]

    def test_anonimo_e_redirecionado_para_login(self):
        for url in self.urls_painel():
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 302, url)
            self.assertIn(reverse('login'), resposta['Location'])

    def test_professor_recebe_403_por_url_direta(self):
        self.entrar(self.prof)
        for url in self.urls_painel():
            self.assertEqual(self.client.get(url).status_code, 403, url)
        resposta = self.client.post(reverse('painel_usuario_alternar_ativo', args=[self.prof2.id]))
        self.assertEqual(resposta.status_code, 403)
        self.prof2.refresh_from_db()
        self.assertTrue(self.prof2.is_active)

    def test_admin_do_grupo_e_superusuario_acessam(self):
        for usuario in (self.admin, self.root):
            self.entrar(usuario)
            for url in self.urls_painel():
                self.assertEqual(self.client.get(url).status_code, 200, f'{usuario} {url}')

    def test_admin_inativo_perde_acesso(self):
        self.admin.is_active = False
        self.admin.save()
        self.assertFalse(is_admin_sigpad(self.admin))

    def test_menu_administracao_so_aparece_para_admin(self):
        self.entrar(self.prof)
        self.assertNotContains(self.client.get(reverse('dashboard')), reverse('painel_dashboard'))
        self.entrar(self.admin)
        self.assertContains(self.client.get(reverse('dashboard')), reverse('painel_dashboard'))

    def test_alternar_ativo_exige_post(self):
        self.entrar(self.admin)
        self.assertEqual(self.client.get(reverse('painel_usuario_alternar_ativo', args=[self.prof.id])).status_code, 405)


class UsuariosPainelTests(BasePainelTestCase):
    def test_cadastrar_professor(self):
        self.entrar(self.admin)
        resposta = self.client.post(reverse('painel_usuario_criar'), {
            'first_name': 'Carla', 'last_name': 'Souza', 'email': 'Carla@Escola.test', 'username': 'carla',
            'senha': SENHA, 'confirmar_senha': SENHA,
        })
        novo = User.objects.get(username='carla')
        self.assertRedirects(resposta, reverse('painel_usuario_detalhes', args=[novo.id]))
        self.assertEqual(novo.email, 'carla@escola.test')
        self.assertTrue(novo.check_password(SENHA))
        self.assertFalse(is_admin_sigpad(novo))
        self.assertTrue(hasattr(novo, 'perfilusuario'))

    def test_cadastro_valida_duplicidade_e_senha(self):
        self.entrar(self.admin)
        resposta = self.client.post(reverse('painel_usuario_criar'), {
            'first_name': 'X', 'email': 'PROF@escola.test', 'username': 'PROF', 'senha': '123', 'confirmar_senha': '123',
        })
        self.assertEqual(resposta.status_code, 200)
        form = resposta.context['form']
        self.assertIn('username', form.errors)
        self.assertIn('email', form.errors)
        self.assertIn('senha', form.errors)

    def test_editar_e_promover_professor(self):
        self.entrar(self.admin)
        self.client.post(reverse('painel_usuario_editar', args=[self.prof.id]), {
            'first_name': 'Ana Maria', 'last_name': 'Lima', 'email': 'prof@escola.test', 'username': 'prof',
            'is_active': 'on', 'administrador': 'on',
        })
        self.prof.refresh_from_db()
        self.assertEqual(self.prof.first_name, 'Ana Maria')
        self.assertTrue(is_admin_sigpad(User.objects.get(pk=self.prof.pk)))

    def test_admin_nao_remove_o_proprio_acesso(self):
        self.entrar(self.admin)
        resposta = self.client.post(reverse('painel_usuario_editar', args=[self.admin.id]), {
            'first_name': 'Coord', 'email': 'coord@escola.test', 'username': 'coord',
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context['form'].errors)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertTrue(self.admin.groups.filter(name=GRUPO_ADMIN).exists())

        self.client.post(reverse('painel_usuario_alternar_ativo', args=[self.admin.id]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_nao_desativa_ultimo_administrador(self):
        self.root.delete()  # sobra apenas "coord" como administrador
        outro = User.objects.create_user('outro', 'outro@escola.test', SENHA)
        outro.groups.add(self.grupo)
        self.entrar(outro)
        self.client.post(reverse('painel_usuario_alternar_ativo', args=[self.admin.id]))
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_active)  # havia outro admin ativo
        outro_resposta = self.client.post(reverse('painel_usuario_editar', args=[outro.id]), {
            'first_name': 'Outro', 'email': 'outro@escola.test', 'username': 'outro', 'is_active': 'on',
        })
        self.assertTrue(outro_resposta.context['form'].errors)  # seria o ultimo admin

    def test_desativar_preserva_dados_e_bloqueia_login(self):
        self.entrar(self.admin)
        self.client.post(reverse('painel_usuario_alternar_ativo', args=[self.prof.id]))
        self.prof.refresh_from_db()
        self.assertFalse(self.prof.is_active)
        self.assertTrue(Turma.objects.filter(pk=self.turma.pk).exists())
        self.client.logout()
        self.assertFalse(self.client.login(username='prof', password=SENHA))

    def test_admin_comum_nao_altera_superusuario(self):
        self.entrar(self.admin)
        self.assertEqual(self.client.get(reverse('painel_usuario_editar', args=[self.root.id])).status_code, 403)
        self.assertEqual(self.client.post(reverse('painel_usuario_alternar_ativo', args=[self.root.id])).status_code, 403)
        self.assertEqual(self.client.get(reverse('painel_usuario_senha', args=[self.root.id])).status_code, 403)
        resposta = self.client.get(reverse('painel_usuario_editar', args=[self.prof.id]))
        self.assertNotIn('is_superuser', resposta.context['form'].fields)

    def test_redefinir_senha(self):
        self.entrar(self.admin)
        nova = 'OutraSenha#2026'
        self.client.post(reverse('painel_usuario_senha', args=[self.prof.id]), {'new_password1': nova, 'new_password2': nova})
        self.prof.refresh_from_db()
        self.assertTrue(self.prof.check_password(nova))

    def test_busca_e_filtros(self):
        self.entrar(self.admin)
        resposta = self.client.get(reverse('painel_usuarios'), {'q': 'bruno'})
        self.assertEqual([u.username for u in resposta.context['pagina']], ['prof2'])
        resposta = self.client.get(reverse('painel_usuarios'), {'papel': 'admin'})
        self.assertEqual({u.username for u in resposta.context['pagina']}, {'coord', 'root'})


class AcademicoPainelTests(BasePainelTestCase):
    def test_criar_turma_para_professor(self):
        self.entrar(self.admin)
        self.client.post(reverse('painel_turma_criar'), {
            'professor': self.prof2.id, 'nome': '  7º   Ano B ', 'ano_letivo': 2026, 'turno': 'VESPERTINO',
        })
        turma = Turma.objects.get(nome='7º Ano B')
        self.assertEqual(turma.professor, self.prof2)

    def test_turma_duplicada_e_recusada(self):
        self.entrar(self.admin)
        resposta = self.client.post(reverse('painel_turma_criar'), {
            'professor': self.prof.id, 'nome': '6º ano a', 'ano_letivo': 2026, 'turno': 'MATUTINO',
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Turma.objects.filter(professor=self.prof, ano_letivo=2026).count(), 1)

    def test_transferir_turma_e_disciplinas(self):
        self.entrar(self.admin)
        self.client.post(reverse('painel_turma_editar', args=[self.turma.id]), {
            'professor': self.prof2.id, 'nome': self.turma.nome, 'ano_letivo': 2026, 'turno': 'MATUTINO',
            'transferir_disciplinas': 'on',
        })
        self.turma.refresh_from_db()
        self.disciplina.refresh_from_db()
        self.assertEqual(self.turma.professor, self.prof2)
        self.assertEqual(self.disciplina.professor, self.prof2)
        # o novo professor passa a ver a turma nas telas existentes
        self.entrar(self.prof2)
        self.assertEqual(self.client.get(reverse('turma_detalhes', args=[self.turma.id])).status_code, 200)

    def test_criar_disciplina_usa_professor_da_turma(self):
        self.entrar(self.admin)
        self.client.post(reverse('painel_disciplina_criar'), {
            'turma': self.turma.id, 'nome': 'Ciências', 'carga_horaria': 80, 'tipo_periodo': 'BIMESTRE',
            'quantidade_aulas': 80, 'nota_total': '10', 'media_aprovacao': '6', 'ano_escolar': '6º ano',
        })
        disciplina = Disciplina.objects.get(nome='Ciências')
        self.assertEqual(disciplina.professor, self.prof)
        self.assertEqual(disciplina.periodos_letivos.count(), 4)

    def test_indicadores_reais_no_dashboard(self):
        self.entrar(self.admin)
        contexto = self.client.get(reverse('painel_dashboard')).context
        self.assertEqual(contexto['total_turmas'], 1)
        self.assertEqual(contexto['total_disciplinas'], 1)
        self.assertEqual(contexto['total_atividades'], 2)
        self.assertEqual(contexto['total_professores'], 2)
        resumo = contexto['resumo']
        # aluno2 faltou 2 de 4 aulas (50%) e tirou 4/10 -> baixa frequencia e abaixo da media
        self.assertEqual(resumo['alunos_baixa_frequencia'], 1)
        self.assertEqual(resumo['alunos_abaixo_media'], 1)
        self.assertEqual(resumo['frequencia_media'], Decimal('75.00'))
        self.assertEqual(resumo['media_geral'], Decimal('6.00'))

    def test_filtros_planejamento(self):
        self.entrar(self.admin)
        resposta = self.client.get(reverse('painel_planejamento'), {'periodo': '1_BIMESTRE'})
        self.assertEqual([a.titulo for a in resposta.context['pagina']], ['Prova'])
        resposta = self.client.get(reverse('painel_planejamento'), {'turma': 'abc', 'ano': '2026'})
        self.assertEqual(resposta.status_code, 200)


class RelatoriosPdfTests(BasePainelTestCase):
    def urls_pdf(self):
        return [
            reverse(nome, args=[self.turma.id]) + f'?disciplina={self.disciplina.id}'
            for nome in ('exportar_notas_pdf', 'exportar_frequencia_pdf', 'relatorio_final')
        ]

    def test_admin_baixa_pdf_de_qualquer_turma(self):
        self.entrar(self.admin)
        for url in self.urls_pdf():
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 200, url)
            self.assertEqual(resposta['Content-Type'], 'application/pdf')

    def test_dono_continua_acessando_e_outro_professor_nao(self):
        self.entrar(self.prof)
        for url in self.urls_pdf():
            self.assertEqual(self.client.get(url).status_code, 200)
        self.entrar(self.prof2)
        for url in self.urls_pdf():
            self.assertEqual(self.client.get(url).status_code, 404)


class TelasExistentesTests(BasePainelTestCase):
    def test_telas_do_professor_continuam_funcionando(self):
        self.entrar(self.prof)
        urls = [
            reverse('dashboard'), reverse('turma_lista'), reverse('disciplina_lista'), reverse('conteudo_lista'),
            reverse('relatorio_lista'), reverse('alerta_lista'), reverse('perfil_usuario'),
            reverse('turma_detalhes', args=[self.turma.id]), reverse('planilha_turma', args=[self.turma.id]),
            reverse('chamada_turma', args=[self.turma.id]), reverse('boletim_turma', args=[self.turma.id]),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_professor_nao_ve_turma_de_outro(self):
        self.entrar(self.prof2)
        self.assertEqual(self.client.get(reverse('turma_detalhes', args=[self.turma.id])).status_code, 404)

    def test_login_existente(self):
        resposta = self.client.post(reverse('login'), {'username': 'prof', 'password': SENHA})
        self.assertRedirects(resposta, reverse('dashboard'))


class ConcederAdminComandoTests(BasePainelTestCase):
    def rodar(self, *args, entrada=None):
        from io import StringIO
        from unittest.mock import patch

        from django.core.management import call_command

        saida = StringIO()
        with patch('builtins.input', return_value=entrada or ''):
            call_command('conceder_admin', *args, stdout=saida)
        return saida.getvalue()

    def estado(self, usuario):
        usuario = User.objects.get(pk=usuario.pk)
        return (usuario.is_active, usuario.is_staff, usuario.is_superuser, usuario.password,
                set(usuario.groups.values_list('name', flat=True)))

    def test_concede_com_confirmacao_sem_mexer_em_mais_nada(self):
        antes_prof, antes_prof2 = self.estado(self.prof), self.estado(self.prof2)
        self.rodar('prof', entrada='prof')
        depois = self.estado(self.prof)
        self.assertEqual(depois[:4], antes_prof[:4])  # ativo, staff, superuser e senha intactos
        self.assertEqual(depois[4], {GRUPO_ADMIN})
        self.assertEqual(self.estado(self.prof2), antes_prof2)  # outra conta intocada
        self.entrar(User.objects.get(pk=self.prof.pk))
        self.assertEqual(self.client.get(reverse('painel_dashboard')).status_code, 200)

    def test_sem_confirmacao_nada_muda(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self.rodar('prof', entrada='nao')
        self.assertFalse(is_admin_sigpad(User.objects.get(pk=self.prof.pk)))

    def test_verificar_e_somente_leitura(self):
        saida = self.rodar('prof', '--verificar')
        self.assertIn('acesso ao /painel/: NAO', saida)
        self.assertFalse(is_admin_sigpad(User.objects.get(pk=self.prof.pk)))

    def test_localiza_por_email_e_confirma_com_sim(self):
        self.rodar('PROF@escola.test', '--email', '--sim')
        self.assertTrue(is_admin_sigpad(User.objects.get(pk=self.prof.pk)))

    def test_usuario_inexistente_nao_e_criado(self):
        from django.core.management.base import CommandError

        total = User.objects.count()
        with self.assertRaises(CommandError):
            self.rodar('fantasma', '--sim')
        self.assertEqual(User.objects.count(), total)

    def test_conta_inativa_e_recusada(self):
        from django.core.management.base import CommandError

        self.prof.is_active = False
        self.prof.save()
        with self.assertRaises(CommandError):
            self.rodar('prof', '--sim')
        self.assertFalse(User.objects.get(pk=self.prof.pk).groups.exists())

    def test_ja_admin_nao_altera(self):
        saida = self.rodar('coord', '--sim')
        self.assertIn('JA tem acesso', saida)


@override_settings(SECURE_SSL_REDIRECT=False)
class DjangoAdminProtegidoTests(BasePainelTestCase):
    def test_admin_do_sigpad_sem_staff_nao_entra_no_django_admin(self):
        self.entrar(self.admin)  # grupo do SIGPAD, sem is_staff
        resposta = self.client.get('/admin/')
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('/admin/login/', resposta['Location'])
        self.entrar(self.prof)
        self.assertEqual(self.client.get('/admin/').status_code, 302)
