from django.db import models
from django.contrib.auth.models import User

from rawstatus import models as filemodels


class GalaxyWorkflow(models.Model):
    commit = models.CharField(max_length=50)
    wfjson = models.TextField()


class GalaxySearch(models.Model):
    searchtype = models.CharField(max_length=10)
    workflow = models.ForeignKey(GalaxyWorkflow)


class GalaxyAccount(models.Model):
    user = models.ForeignKey(User)
    apikey = models.CharField(max_length=32)


class Analysis(models.Model):
    date = models.DateTimeField()
    user = models.ForeignKey(User)
    name = models.CharField(max_length=100)
    search = models.ForeignKey(GalaxySearch)
    account = models.ForeignKey(GalaxyAccount)
    params = models.TextField()  # Json


class SearchMzmlFiles(models.Model):
    analysis = models.ForeignKey(Analysis)
    mzml = models.ForeignKey(filemodels.StoredFile)


class GalaxyResult(models.Model):
    analysis = models.ForeignKey(Analysis)


class GalaxyLibrary(models.Model):
    name = models.CharField(max_length=100)
    galaxy_id = models.CharField(max_length=16)


class GalaxyLibDataset(models.Model):
    name = models.CharField(max_length=100)
    galaxy_id = models.CharField(max_length=16)
    library_id = models.ForeignKey(GalaxyLibrary)
    active = models.BooleanField(default=True)


class QCParams(models.Model):
    """Fixed params for QC runs: target, decoy DB, not instrument etc
    paramjson = {'target db': GalaxyLibDataset.id, 'decoy db': etc"""
    creationdate = models.DateTimeField(auto_now=True)
    paramjson = models.TextField()
