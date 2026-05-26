from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User

from .models import (
    Aluno,
    AnotacaoTurma,
    Aula,
    Chamada,
    ConteudoProgramatico,
    Disciplina,
    PerfilUsuario,
    ProcessoAvaliativo,
    Turma,
)


class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})


PERIODO_CHOICES_POR_TIPO = {
    'BIMESTRE': [
        ('1_BIMESTRE', '1º bimestre'),
        ('2_BIMESTRE', '2º bimestre'),
        ('3_BIMESTRE', '3º bimestre'),
        ('4_BIMESTRE', '4º bimestre'),
    ],
    'TRIMESTRE': [
        ('1_TRIMESTRE', '1º trimestre'),
        ('2_TRIMESTRE', '2º trimestre'),
        ('3_TRIMESTRE', '3º trimestre'),
    ],
    'SEMESTRE': [
        ('1_SEMESTRE', '1º semestre'),
        ('2_SEMESTRE', '2º semestre'),
    ],
    'ANUAL': [
        ('ANUAL', 'Anual'),
    ],
}


class DisciplinaForm(BootstrapModelForm):
    class Meta:
        model = Disciplina
        fields = [
            'turma',
            'nome',
            'descricao',
            'carga_horaria',
            'tipo_periodo',
            'quantidade_aulas',
            'nota_total',
            'media_aprovacao',
            'ano_escolar',
        ]
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        professor = kwargs.pop('professor', None)
        turma = kwargs.pop('turma', None)
        super().__init__(*args, **kwargs)
        self.fields['turma'].required = True
        if turma is not None:
            self.fields.pop('turma')
        elif professor is not None:
            self.fields['turma'].queryset = Turma.objects.filter(professor=professor)
        if not self.initial.get('quantidade_aulas') and self.instance and self.instance.pk:
            self.initial['quantidade_aulas'] = self.instance.quantidade_aulas or self.instance.carga_horaria


class TurmaForm(BootstrapModelForm):
    class Meta:
        model = Turma
        fields = ['nome', 'ano_letivo', 'turno', 'descricao']
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_nome(self):
        return ' '.join(self.cleaned_data['nome'].split())


class ConteudoProgramaticoForm(BootstrapModelForm):
    class Meta:
        model = ConteudoProgramatico
        fields = [
            'disciplina',
            'titulo',
            'descricao',
            'unidade',
            'periodo',
            'bimestre',
            'data_inicio',
            'data_fim',
            'arquivo',
            'concluido',
        ]
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 4}),
            'data_inicio': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'data_fim': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        professor = kwargs.pop('professor', None)
        turma = kwargs.pop('turma', None)
        super().__init__(*args, **kwargs)
        disciplinas = Disciplina.objects.all()
        if professor is not None:
            disciplinas = disciplinas.filter(professor=professor)
        if turma is not None:
            disciplinas = disciplinas.filter(turma=turma)
        self.fields['disciplina'].queryset = disciplinas
        self.fields['disciplina'].label_from_instance = (
            lambda disciplina: f'{disciplina.turma.nome} - {disciplina.nome}' if disciplina.turma else disciplina.nome
        )
        self.fields['bimestre'].help_text = 'Campo antigo mantido para compatibilidade.'
        self.fields['concluido'].widget.attrs.update({'class': 'form-check-input'})
        self._filtrar_periodo_por_disciplina(turma)

    def _filtrar_periodo_por_disciplina(self, turma=None):
        disciplina = None
        disciplina_id = self.data.get('disciplina') if self.is_bound else self.initial.get('disciplina')
        if self.instance and self.instance.pk:
            disciplina = self.instance.disciplina
        elif turma is not None and self.fields['disciplina'].queryset.count() == 1:
            disciplina = self.fields['disciplina'].queryset.first()
        elif disciplina_id:
            disciplina = self.fields['disciplina'].queryset.filter(pk=disciplina_id).first()
        choices = PERIODO_CHOICES_POR_TIPO.get(getattr(disciplina, 'tipo_periodo', None), [])
        self.fields['periodo'].choices = choices
        if choices and len(choices) == 1:
            self.fields['periodo'].initial = choices[0][0]

    def save(self, commit=True):
        conteudo = super().save(commit=False)
        if conteudo.disciplina_id:
            conteudo.tipo_periodo = conteudo.disciplina.tipo_periodo
            if conteudo.tipo_periodo == 'ANUAL':
                conteudo.periodo = 'ANUAL'
        if commit:
            conteudo.save()
            self.save_m2m()
        return conteudo


class AnotacaoTurmaForm(BootstrapModelForm):
    class Meta:
        model = AnotacaoTurma
        fields = ['titulo', 'descricao']
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 5}),
        }


class AlunoForm(BootstrapModelForm):
    class Meta:
        model = Aluno
        fields = ['nome', 'matricula', 'ativo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ativo'].widget.attrs.update({'class': 'form-check-input'})


class ProcessoAvaliativoForm(BootstrapModelForm):
    class Meta:
        model = ProcessoAvaliativo
        fields = ['disciplina', 'periodo', 'titulo', 'tipo', 'valor_maximo', 'data', 'descricao']
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 4}),
            'data': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        turma = kwargs.pop('turma', None)
        super().__init__(*args, **kwargs)
        if turma is not None:
            self.fields['disciplina'].queryset = Disciplina.objects.filter(turma=turma)
        self._filtrar_periodo_por_disciplina(turma)

    def _filtrar_periodo_por_disciplina(self, turma=None):
        disciplina = None
        disciplina_id = self.data.get('disciplina') if self.is_bound else self.initial.get('disciplina')
        if self.instance and self.instance.pk:
            disciplina = self.instance.disciplina
        elif turma is not None and self.fields['disciplina'].queryset.count() == 1:
            disciplina = self.fields['disciplina'].queryset.first()
        elif disciplina_id:
            disciplina = self.fields['disciplina'].queryset.filter(pk=disciplina_id).first()
        choices = PERIODO_CHOICES_POR_TIPO.get(getattr(disciplina, 'tipo_periodo', None), [])
        self.fields['periodo'].choices = choices
        if choices and len(choices) == 1:
            self.fields['periodo'].initial = choices[0][0]

    def save(self, commit=True):
        avaliacao = super().save(commit=False)
        if avaliacao.disciplina_id:
            avaliacao.tipo_periodo = avaliacao.disciplina.tipo_periodo
            if avaliacao.tipo_periodo == 'ANUAL':
                avaliacao.periodo = 'ANUAL'
        if commit:
            avaliacao.full_clean()
            avaliacao.save()
            self.save_m2m()
        return avaliacao


class CadastroProfessorForm(forms.Form):
    nome = forms.CharField(max_length=150)
    sobrenome = forms.CharField(max_length=150)
    email = forms.EmailField()
    username = forms.CharField(max_length=150)
    senha = forms.CharField(widget=forms.PasswordInput)
    confirmar_senha = forms.CharField(widget=forms.PasswordInput)
    foto = forms.ImageField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('Este nome de usuario ja esta em uso.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Este email ja esta em uso.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        senha = cleaned_data.get('senha')
        confirmar_senha = cleaned_data.get('confirmar_senha')
        if senha and confirmar_senha and senha != confirmar_senha:
            raise forms.ValidationError('As senhas nao conferem.')
        return cleaned_data

    def save(self):
        user = User(
            first_name=self.cleaned_data['nome'].strip(),
            last_name=self.cleaned_data['sobrenome'].strip(),
            email=self.cleaned_data['email'],
            username=self.cleaned_data['username'],
        )
        user.set_password(self.cleaned_data['senha'])
        user.save()
        perfil, _ = PerfilUsuario.objects.get_or_create(usuario=user)
        foto = self.cleaned_data.get('foto')
        if foto:
            perfil.foto = foto
            perfil.save(update_fields=['foto'])
        return user


class ChamadaForm(BootstrapModelForm):
    class Meta:
        model = Chamada
        fields = ['disciplina', 'data', 'tipo_periodo', 'periodo', 'descricao']
        widgets = {
            'data': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        turma = kwargs.pop('turma', None)
        super().__init__(*args, **kwargs)
        if turma is not None:
            self.fields['disciplina'].queryset = Disciplina.objects.filter(turma=turma)


class AulaForm(BootstrapModelForm):
    class Meta:
        model = Aula
        fields = ['disciplina', 'data', 'quantidade_aulas', 'conteudo_aplicado', 'observacao']
        widgets = {
            'data': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'conteudo_aplicado': forms.Textarea(attrs={'rows': 4}),
            'observacao': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        turma = kwargs.pop('turma', None)
        super().__init__(*args, **kwargs)
        if turma is not None:
            self.fields['disciplina'].queryset = Disciplina.objects.filter(turma=turma)


class UsuarioPerfilForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }


class PerfilUsuarioForm(forms.ModelForm):
    class Meta:
        model = PerfilUsuario
        fields = ['foto']
        widgets = {
            'foto': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


class AlterarSenhaForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label='Usuario',
        widget=forms.TextInput(attrs={'class': 'form-control', 'autofocus': True}),
    )
    password = forms.CharField(
        label='Senha',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )
