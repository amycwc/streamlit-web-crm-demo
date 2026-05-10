# Generated migration for CustomerSegment model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('crm_model', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomerSegment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recency_days', models.IntegerField(blank=True, null=True)),
                ('frequency', models.IntegerField(blank=True, null=True)),
                ('monetary', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('r_score', models.IntegerField(blank=True, null=True)),
                ('f_score', models.IntegerField(blank=True, null=True)),
                ('m_score', models.IntegerField(blank=True, null=True)),
                ('rfm_score', models.IntegerField(blank=True, null=True)),
                ('segment', models.CharField(blank=True, max_length=64, null=True)),
                ('last_calculated', models.DateTimeField(auto_now=True)),
                ('customer', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='segment', to='crm_model.customerprofile')),
            ],
            options={
                'verbose_name': 'Customer Segment',
                'verbose_name_plural': 'Customer Segments',
            },
        ),
    ]
