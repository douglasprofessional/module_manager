# Integração com a Google Places API (New) e o motor de análise/IA.
#
# - ConfiguracaoProspeccao: singleton do Painel do módulo (chave do Google e
#   da IA cifradas, modelo de IA e limites do motor de análise).
# - Busca.conexao passa a ser opcional (sem conexão = chave do Painel).
# - Empresa recebe as métricas do Places (nota, avaliações, fotos, situação,
#   horário, última atividade) e os diagnósticos (regras e IA).
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prospeccao", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConfiguracaoProspeccao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "chave_google_criptografada",
                    models.TextField(blank=True, default="", verbose_name="chave da Google Places API (cifrada)"),
                ),
                (
                    "ia_chave_criptografada",
                    models.TextField(blank=True, default="", verbose_name="chave da API de IA (cifrada)"),
                ),
                ("ia_modelo", models.CharField(default="claude-opus-5-5", max_length=80, verbose_name="modelo de IA")),
                ("ia_ativa", models.BooleanField(default=True, verbose_name="IA generativa ativa")),
                (
                    "limiar_nota",
                    models.FloatField(
                        default=4.0,
                        validators=[
                            django.core.validators.MinValueValidator(0.0),
                            django.core.validators.MaxValueValidator(5.0),
                        ],
                        verbose_name="nota mínima",
                    ),
                ),
                ("limiar_avaliacoes", models.PositiveIntegerField(default=5, verbose_name="mínimo de avaliações")),
                (
                    "limiar_fotos",
                    models.PositiveSmallIntegerField(
                        default=3,
                        validators=[django.core.validators.MaxValueValidator(10)],
                        verbose_name="mínimo de fotos",
                    ),
                ),
                (
                    "limiar_meses",
                    models.PositiveSmallIntegerField(
                        default=6,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(60),
                        ],
                        verbose_name="meses sem atualização",
                    ),
                ),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
            ],
            options={
                "verbose_name": "configuração da prospecção",
                "verbose_name_plural": "configuração da prospecção",
            },
        ),
        migrations.AlterField(
            model_name="busca",
            name="conexao",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="buscas",
                to="prospeccao.conexaogoogle",
                verbose_name="conexão",
            ),
        ),
        migrations.AddField(
            model_name="empresa",
            name="nota_google",
            field=models.FloatField(blank=True, null=True, verbose_name="nota no Google"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="total_avaliacoes",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="total de avaliações"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="total_fotos",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="total de fotos"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="status_google",
            field=models.CharField(blank=True, default="", max_length=30, verbose_name="situação no Google"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="situacao_horario",
            field=models.CharField(blank=True, default="", max_length=12, verbose_name="situação do horário"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="horario_semana",
            field=models.JSONField(blank=True, default=list, verbose_name="horário da semana"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="ultima_atividade_perfil",
            field=models.DateField(blank=True, null=True, verbose_name="última atividade do perfil"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="google_maps_url",
            field=models.URLField(blank=True, default="", max_length=500, verbose_name="link do Google Maps"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="analisado_places_em",
            field=models.DateTimeField(blank=True, null=True, verbose_name="analisado no Google Places em"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="diagnostico",
            field=models.TextField(blank=True, default="", verbose_name="diagnóstico do motor de análise"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="diagnostico_ia",
            field=models.TextField(blank=True, default="", verbose_name="diagnóstico da IA"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="diagnostico_ia_em",
            field=models.DateTimeField(blank=True, null=True, verbose_name="diagnóstico da IA gerado em"),
        ),
    ]
