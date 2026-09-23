"""
Give every existing advisor a sign-in account.

The advisors predate authentication, so they exist as bare names with no way to
log in. This creates one auth User per Advisor and links them.

Every account is created with the same placeholder password, which the project
chose deliberately so the team can sign in while this is still being built. It
is a placeholder, not a credential: anyone who can reach the server knows it, so
until each account has its own password this login keeps out a passer-by and
nobody else. Change them in the Django admin, or with

    python manage.py changepassword <username>

New advisors added later get an account the same way - through the admin - not
through this migration.
"""
from django.contrib.auth.hashers import make_password
from django.db import migrations

PLACEHOLDER_PASSWORD = "admin"


def create_users(apps, schema_editor):
    Advisor = apps.get_model("rag_api", "Advisor")
    User = apps.get_model("auth", "User")

    # Hash once: each call runs the full PBKDF2 work factor, and this is the
    # same password for every row anyway.
    hashed = make_password(PLACEHOLDER_PASSWORD)

    for advisor in Advisor.objects.filter(user__isnull=True):
        # Usernames are lowercased so signing in is not case-sensitive, while
        # Advisor.name stays as it is - it is what Pinecone's owner field and
        # the audit logs are keyed on.
        username = advisor.name.lower()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"password": hashed, "is_active": True},
        )
        if not created and not user.password:
            user.password = hashed
            user.save(update_fields=["password"])
        advisor.user = user
        advisor.save(update_fields=["user"])


def unlink_users(apps, schema_editor):
    Advisor = apps.get_model("rag_api", "Advisor")
    User = apps.get_model("auth", "User")

    names = list(Advisor.objects.exclude(user__isnull=True)
                 .values_list("user__username", flat=True))
    Advisor.objects.update(user=None)
    # Leave superusers alone; they were not created here.
    User.objects.filter(username__in=names, is_superuser=False).delete()


class Migration(migrations.Migration):
    dependencies = [("rag_api", "0005_add_user_to_advisor")]
    operations = [migrations.RunPython(create_users, unlink_users)]
