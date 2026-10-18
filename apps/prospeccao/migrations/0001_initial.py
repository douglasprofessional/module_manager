# Migração inicial do módulo de prospecção.
#
# Reproduz EXATAMENTE o esquema que o ``makemigrations`` gerava em tempo de
# execução (antes da integração com a Google Places API). Bancos que já
# rodaram essa migração gerada no boot a têm registrada como
# "prospeccao.0001_initial" e simplesmente seguem para a 0002; bancos novos
# aplicam as duas. Assim a evolução do esquema funciona nos dois casos.
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ConexaoGoogle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=120, verbose_name="nome")),
                (
                    "chave_api_criptografada",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Token cifrado (Fernet). Nunca armazenar a chave em texto.",
                        verbose_name="chave da API (cifrada)",
                    ),
                ),
                ("ativo", models.BooleanField(default=True, verbose_name="ativo")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                (
                    "criado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="conexoes_google",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="criado por",
                    ),
                ),
            ],
            options={
                "verbose_name": "conexão Google",
                "verbose_name_plural": "conexões Google",
                "ordering": ("-criado_em",),
            },
        ),
        migrations.CreateModel(
            name="Busca",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("termo", models.CharField(max_length=200, verbose_name="termo")),
                ("localizacao", models.CharField(max_length=200, verbose_name="localização")),
                ("raio_metros", models.PositiveIntegerField(default=5000, verbose_name="raio (metros)")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pendente", "Pendente"),
                            ("executando", "Executando"),
                            ("concluida", "Concluída"),
                            ("erro", "Erro"),
                        ],
                        default="pendente",
                        max_length=20,
                        verbose_name="status",
                    ),
                ),
                ("total_resultados", models.PositiveIntegerField(default=0, verbose_name="total de resultados")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                (
                    "conexao",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="buscas",
                        to="prospeccao.conexaogoogle",
                        verbose_name="conexão",
                    ),
                ),
                (
                    "criado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="buscas",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="criado por",
                    ),
                ),
            ],
            options={
                "verbose_name": "busca",
                "verbose_name_plural": "buscas",
                "ordering": ("-criado_em",),
            },
        ),
        migrations.CreateModel(
            name="Empresa",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "place_id",
                    models.CharField(blank=True, max_length=255, null=True, unique=True, verbose_name="place_id"),
                ),
                ("nome", models.CharField(max_length=255, verbose_name="nome")),
                ("categoria", models.CharField(blank=True, default="", max_length=150, verbose_name="categoria")),
                ("endereco", models.CharField(blank=True, default="", max_length=255, verbose_name="endereço")),
                ("telefone", models.CharField(blank=True, default="", max_length=50, verbose_name="telefone")),
                ("whatsapp", models.CharField(blank=True, default="", max_length=50, verbose_name="whatsapp")),
                ("email", models.EmailField(blank=True, default="", max_length=254, verbose_name="e-mail")),
                ("instagram", models.CharField(blank=True, default="", max_length=120, verbose_name="instagram")),
                ("website", models.URLField(blank=True, default="", max_length=300, verbose_name="website")),
                ("dominio", models.CharField(blank=True, default="", max_length=255, verbose_name="domínio")),
                ("tem_site", models.BooleanField(default=False, verbose_name="tem site")),
                ("site_desatualizado", models.BooleanField(default=False, verbose_name="site desatualizado")),
                ("apenas_instagram", models.BooleanField(default=False, verbose_name="apenas Instagram")),
                ("tem_ssl", models.BooleanField(blank=True, null=True, verbose_name="tem SSL")),
                ("hospedagem_sem_site", models.BooleanField(default=False, verbose_name="hospedagem sem site")),
                (
                    "score_seo",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        null=True,
                        validators=[django.core.validators.MaxValueValidator(100)],
                        verbose_name="score de SEO",
                    ),
                ),
                (
                    "score_performance",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        null=True,
                        validators=[django.core.validators.MaxValueValidator(100)],
                        verbose_name="score de performance",
                    ),
                ),
                ("data_fundacao", models.DateField(blank=True, null=True, verbose_name="data de fundação")),
                (
                    "tempo_mercado_texto",
                    models.CharField(blank=True, default="", max_length=100, verbose_name="tempo de mercado"),
                ),
                ("responsavel", models.CharField(blank=True, default="", max_length=150, verbose_name="responsável")),
                (
                    "cargo_responsavel",
                    models.CharField(blank=True, default="", max_length=100, verbose_name="cargo do responsável"),
                ),
                ("latitude", models.FloatField(blank=True, null=True, verbose_name="latitude")),
                ("longitude", models.FloatField(blank=True, null=True, verbose_name="longitude")),
                (
                    "status_prospeccao",
                    models.CharField(
                        choices=[
                            ("nova", "Nova"),
                            ("qualificada", "Qualificada"),
                            ("contatada", "Contatada"),
                            ("descartada", "Descartada"),
                        ],
                        default="nova",
                        max_length=20,
                        verbose_name="status da prospecção",
                    ),
                ),
                (
                    "oportunidade_score",
                    models.PositiveSmallIntegerField(
                        default=0,
                        validators=[django.core.validators.MaxValueValidator(100)],
                        verbose_name="score de oportunidade",
                    ),
                ),
                ("observacoes", models.TextField(blank=True, default="", verbose_name="observações")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                (
                    "busca",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="empresas",
                        to="prospeccao.busca",
                        verbose_name="busca",
                    ),
                ),
            ],
            options={
                "verbose_name": "empresa",
                "verbose_name_plural": "empresas",
                "ordering": ("-oportunidade_score", "-criado_em"),
                "indexes": [
                    models.Index(fields=["status_prospeccao"], name="prospeccao__status__9d9747_idx"),
                    models.Index(fields=["-oportunidade_score"], name="prospeccao__oportun_466a73_idx"),
                ],
            },
        ),
    ]
