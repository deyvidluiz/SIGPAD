"""Formularios da area administrativa (/painel/)."""

from django import forms
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password

from .forms import DisciplinaForm, TurmaForm
from .permissoes import GRUPO_ADMIN, is_admin_sigpad


def _bootstrap(form):
    for field in form.fields.values():
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs.update({'class': 'form-check-input'})
        else:
            field.widget.attrs.setdefault('class', 'form-control')


def usuarios_ativos():
    return User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'username')


class ProfessorChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, usuario):
        nome = usuario.get_full_name()
        return f'{nome} ({usuario.username})' if nome else usuario.username


def administradores_ativos():
    return User.objects.filter(is_active=True).filter(
        is_superuser=True,
    ) | User.objects.filter(is_active=True, groups__name=GRUPO_ADMIN)


class UsuarioBaseForm(forms.ModelForm):
    administrador = forms.BooleanField(
        label='Administrador do SIGPAD',
        required=False,
        help_text='Permite acessar a area administrativa (/painel/).',
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'username']
        labels = {'first_name': 'Nome', 'last_name': 'Sobrenome', 'email': 'E-mail', 'username': 'Usuario'}

    def __init__(self, *args, editor=None, **kwargs):
        self.editor = editor
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['email'].required = True
        _bootstrap(self)

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        existentes = User.objects.filter(username__iexact=username)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise forms.ValidationError('Este nome de usuario ja esta em uso.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        existentes = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise forms.ValidationError('Este e-mail ja esta em uso.')
        return email

    def _aplicar_papel(self, usuario):
        grupo, _ = Group.objects.get_or_create(name=GRUPO_ADMIN)
        if self.cleaned_data.get('administrador'):
            usuario.groups.add(grupo)
        else:
            usuario.groups.remove(grupo)


class UsuarioCriarForm(UsuarioBaseForm):
    senha = forms.CharField(label='Senha', widget=forms.PasswordInput, strip=False)
    confirmar_senha = forms.CharField(label='Confirmar senha', widget=forms.PasswordInput, strip=False)

    def clean(self):
        dados = super().clean()
        senha, confirmar = dados.get('senha'), dados.get('confirmar_senha')
        if senha and confirmar and senha != confirmar:
            self.add_error('confirmar_senha', 'As senhas nao conferem.')
        elif senha:
            usuario = User(
                username=dados.get('username') or '', email=dados.get('email') or '',
                first_name=dados.get('first_name') or '', last_name=dados.get('last_name') or '',
            )
            try:
                validate_password(senha, usuario)
            except forms.ValidationError as erro:
                self.add_error('senha', erro)
        return dados

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.set_password(self.cleaned_data['senha'])
        usuario.is_active = True
        if commit:
            usuario.save()  # o signal cria o PerfilUsuario
            self._aplicar_papel(usuario)
        return usuario


class UsuarioEditarForm(UsuarioBaseForm):
    is_active = forms.BooleanField(label='Conta ativa', required=False)
    is_superuser = forms.BooleanField(
        label='Superusuario',
        required=False,
        help_text='Acesso total, inclusive ao Django Admin. So superusuarios podem alterar este campo.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        usuario = self.instance
        self.fields['is_active'].initial = usuario.is_active
        self.fields['is_superuser'].initial = usuario.is_superuser
        self.fields['administrador'].initial = usuario.groups.filter(name=GRUPO_ADMIN).exists()
        if not (self.editor and self.editor.is_superuser):
            del self.fields['is_superuser']

    def clean(self):
        dados = super().clean()
        usuario = self.instance
        ativo = dados.get('is_active', usuario.is_active)
        superusuario = dados.get('is_superuser', usuario.is_superuser)
        admin = bool(dados.get('administrador')) or superusuario
        continua_admin = ativo and admin

        if self.editor and usuario.pk == self.editor.pk:
            if not ativo:
                self.add_error('is_active', 'Voce nao pode desativar a propria conta.')
            if not continua_admin:
                self.add_error('administrador', 'Voce nao pode remover o seu proprio acesso administrativo.')

        if is_admin_sigpad(usuario) and not continua_admin:
            outros = administradores_ativos().exclude(pk=usuario.pk).distinct()
            if not outros.exists():
                raise forms.ValidationError('O SIGPAD precisa manter pelo menos um administrador ativo.')
        return dados

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.is_active = self.cleaned_data.get('is_active', usuario.is_active)
        if 'is_superuser' in self.fields:
            usuario.is_superuser = self.cleaned_data['is_superuser']
        if commit:
            usuario.save()
            self._aplicar_papel(usuario)
        return usuario


class TurmaPainelForm(TurmaForm):
    """Reaproveita o TurmaForm do professor e permite escolher o professor responsavel."""

    professor = ProfessorChoiceField(queryset=User.objects.none(), label='Professor responsavel')
    transferir_disciplinas = forms.BooleanField(
        label='Transferir tambem as disciplinas desta turma para o novo professor',
        required=False,
        initial=True,
        help_text='No SIGPAD o professor so gerencia as disciplinas das turmas que sao dele.',
    )

    class Meta(TurmaForm.Meta):
        fields = ['professor', 'nome', 'ano_letivo', 'turno', 'descricao']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = usuarios_ativos()
        if self.instance.pk:  # mantem o professor atual mesmo se estiver inativo
            queryset = (queryset | User.objects.filter(pk=self.instance.professor_id)).distinct()
        else:
            del self.fields['transferir_disciplinas']
        self.fields['professor'].queryset = queryset.order_by('first_name', 'last_name', 'username')
        _bootstrap(self)

    def clean(self):
        dados = super().clean()
        professor, nome, ano = dados.get('professor'), dados.get('nome'), dados.get('ano_letivo')
        if professor and nome and ano:
            duplicadas = type(self.instance).objects.filter(professor=professor, nome__iexact=nome, ano_letivo=ano)
            if self.instance.pk:
                duplicadas = duplicadas.exclude(pk=self.instance.pk)
            if duplicadas.exists():
                raise forms.ValidationError('Este professor ja possui uma turma com esse nome nesse ano letivo.')
        return dados


class DisciplinaPainelForm(DisciplinaForm):
    """Reaproveita o DisciplinaForm; o professor da disciplina e o professor da turma."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['turma'].queryset = self.fields['turma'].queryset.model.objects.select_related('professor').order_by(
            '-ano_letivo', 'nome',
        )
        self.fields['turma'].label_from_instance = (
            lambda turma: f'{turma.nome} - {turma.ano_letivo} ({turma.professor.get_full_name() or turma.professor.username})'
        )
        self.fields['turma'].help_text = 'A disciplina fica vinculada ao professor responsavel pela turma.'

    def save(self, commit=True):
        disciplina = super().save(commit=False)
        disciplina.professor = disciplina.turma.professor
        if commit:
            disciplina.save()
        return disciplina
