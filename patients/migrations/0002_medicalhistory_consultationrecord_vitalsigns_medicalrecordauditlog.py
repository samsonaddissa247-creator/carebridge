from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MedicalHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('previous_conditions', models.TextField(blank=True)),
                ('past_illnesses', models.TextField(blank=True)),
                ('previous_operations', models.TextField(blank=True)),
                ('known_allergies', models.TextField(blank=True)),
                ('family_history', models.TextField(blank=True)),
                ('other_information', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='medical_histories', to='patients.patient')),
                ('recorded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='medical_histories_recorded', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='ConsultationRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('consultation_datetime', models.DateTimeField()),
                ('presenting_complaint', models.TextField()),
                ('symptoms', models.TextField(blank=True)),
                ('clinical_observations', models.TextField(blank=True)),
                ('assessment', models.TextField(blank=True)),
                ('notes', models.TextField(blank=True)),
                ('follow_up_instructions', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='consultations_created', to=settings.AUTH_USER_MODEL)),
                ('doctor', models.ForeignKey(blank=True, limit_choices_to={'role': 'DOCTOR'}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='consultations_done', to=settings.AUTH_USER_MODEL)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='consultations', to='patients.patient')),
            ],
            options={
                'ordering': ['-consultation_datetime'],
            },
        ),
        migrations.CreateModel(
            name='VitalSigns',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recorded_at', models.DateTimeField()),
                ('blood_pressure', models.CharField(blank=True, max_length=20)),
                ('temperature', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True)),
                ('pulse_rate', models.IntegerField(blank=True, null=True)),
                ('respiratory_rate', models.IntegerField(blank=True, null=True)),
                ('oxygen_saturation', models.IntegerField(blank=True, null=True)),
                ('weight_kg', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vital_signs', to='patients.patient')),
                ('recorded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vital_signs_recorded', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-recorded_at'],
            },
        ),
        migrations.CreateModel(
            name='MedicalRecordAuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(max_length=80)),
                ('details', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='medical_record_actions', to=settings.AUTH_USER_MODEL)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='medical_record_audit_logs', to='patients.patient')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
