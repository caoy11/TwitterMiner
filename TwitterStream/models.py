from django.db import models

# Create your models here.
class Tweet(models.Model):
    date = models.DateTimeField()
    content = models.TextField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    topic = models.TextField()