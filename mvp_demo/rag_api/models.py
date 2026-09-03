from django.db import models


class Fund(models.Model):
    """A superannuation fund. Document visibility is scoped by these."""
    name = models.CharField(max_length=200, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Advisor(models.Model):
    """
    An advisor using the chatbot.

    This replaces the hardcoded dict that used to live in users.py. There is
    deliberately no password here yet - identity is still supplied by the
    client. When real authentication lands this should become a OneToOne with
    django.contrib.auth.User rather than an identity of its own.
    """
    name = models.CharField(max_length=100, unique=True)
    funds = models.ManyToManyField(Fund, related_name="advisors", blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def fund_names(self):
        return list(self.funds.values_list("name", flat=True))


class Document(models.Model):
    """
    An uploaded PDF and the state of its ingestion.

    Ingestion runs in a background thread, so this row doubles as the job
    record - status/error/chunk_count are what the UI polls. Keeping it in the
    database rather than in memory means progress survives a restart.
    """
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (PROCESSING, "Processing"),
        (READY, "Ready"),
        (FAILED, "Failed"),
    ]

    owner = models.ForeignKey(Advisor, on_delete=models.CASCADE, related_name="documents")
    fund = models.ForeignKey(Fund, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="documents")

    original_filename = models.CharField(max_length=255)
    stored_path = models.CharField(max_length=500)
    doc_type = models.CharField(max_length=100, default="Uploaded")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    error = models.TextField(blank=True, default="")
    chunk_count = models.IntegerField(default=0)

    # Pinecone ids for this document's chunks, so deleting the row can also
    # remove its vectors. The bulk ingest script has no such record, which is
    # why documents it added cannot currently be removed.
    vector_ids = models.JSONField(default=list, blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.owner.name}, {self.status})"
