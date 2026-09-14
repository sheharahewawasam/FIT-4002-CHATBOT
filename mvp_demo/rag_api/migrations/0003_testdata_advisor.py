"""
Give the TestData funds an advisor who can actually reach them.

The TestData/ documents were ingested with correct fund_name metadata, but the
funds were never added to the database and no advisor was granted access. The
Pinecone filter is an exact match on fund_name, so every question about those
funds returned "I cannot find information about this" - the content was indexed
and unreachable at the same time.

The names below are copied from the fund_name values actually present in the
index. They must match exactly: "Darto Super Fund" is stored that way, not
"DARTO", and a mismatch silently returns nothing rather than erroring.

General is included deliberately. It holds the SIS Act and the legislative
changes timeline, and a good number of the deed questions ask whether a deed is
consistent with current law - which needs both sides in the same context.
"""
from django.db import migrations

ADVISOR = "TestAdvisor"

FUNDS = [
    "A and C Super Fund",
    "Andres Family Superannuation Fund",
    "Bell Family Superannuation Fund",
    "Darto Super Fund",
    "Powell Superannuation Fund",
    "General",
]


def add_test_advisor(apps, schema_editor):
    Advisor = apps.get_model("rag_api", "Advisor")
    Fund = apps.get_model("rag_api", "Fund")

    funds = []
    for name in FUNDS:
        fund, _ = Fund.objects.get_or_create(name=name)
        funds.append(fund)

    advisor, _ = Advisor.objects.get_or_create(name=ADVISOR)
    advisor.funds.set(funds)


def remove_test_advisor(apps, schema_editor):
    Advisor = apps.get_model("rag_api", "Advisor")
    Fund = apps.get_model("rag_api", "Fund")

    Advisor.objects.filter(name=ADVISOR).delete()
    # Leave "General" alone - it predates this migration and other advisers use it.
    Fund.objects.filter(name__in=[f for f in FUNDS if f != "General"]).delete()


class Migration(migrations.Migration):
    dependencies = [("rag_api", "0002_seed_advisors_and_funds")]
    operations = [migrations.RunPython(add_test_advisor, remove_test_advisor)]
