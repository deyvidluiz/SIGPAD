from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User

from .models import AnotacaoTurma, ConteudoProgramatico, Disciplina, PerfilUsuario, Turma


class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})


class DisciplinaForm(BootstrapModelForm):
    class Meta:
        model = Disciplina
        fields = ['turma', 'nome', 'descricao', 'carga_horaria', 'ano_escolar']
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
            'tipo_periodo',
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


class AnotacaoTurmaForm(BootstrapModelForm):
    class Meta:
        model = AnotacaoTurma
        fields = ['titulo', 'descricao']
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 5}),
        }


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
