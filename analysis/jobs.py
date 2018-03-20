from datetime import datetime
import json

from kantele import settings
from analysis import tasks, models
from rawstatus import models as filemodels
from datasets import models as dsmodels
from jobs.models import Task

# FIXMEs
# DONE? search must wait for convert, why does it not?
# DONE? store qc data does not finish tasks
# rerun qc data and displaying qcdata for a given qc file, how? 
# run should check if already ran with same commit/analysis



def auto_run_qc_workflow(job_id, sf_id, analysis_id, wfv_id, dbfn_id):
    """Assumes one file, one analysis"""
    analysis = models.Analysis.objects.get(pk=analysis_id)
    nfwf = models.NextflowWfVersion.objects.get(pk=wfv_id)
    dbfn = models.LibraryFile.objects.get(pk=dbfn_id).sfile
    mzml = filemodels.StoredFile.objects.select_related(
        'rawfile__producer', 'servershare').get(rawfile__storedfile__id=sf_id,
                                                filetype='mzml')
    params = ['--mods', 'data/labelfreemods.txt', '--instrument']
    params.append('velos' if 'elos' in mzml.rawfile.producer.name else 'qe')
    stagefiles = {'--mzml': (mzml.servershare.name, mzml.path, mzml.filename),
                  '--db': (dbfn.servershare.name, dbfn.path, dbfn.filename)}
    run = {'timestamp': datetime.strftime(analysis.date, '%Y%m%d_%H.%M'),
           'analysis_id': analysis.id,
           'rf_id': mzml.rawfile_id,
           'wf_commit': nfwf.commit,
           'nxf_wf_fn': nfwf.filename,
           'repo': nfwf.nfworkflow.repo,
           }
    create_nf_search_entries(analysis, nfwf, job_id)
    res = tasks.run_nextflow_longitude_qc.delay(run, params, stagefiles)
    Task.objects.create(asyncid=res.id, job_id=job_id, state='PENDING')


def run_ipaw_getfiles(dset_id, analysis_id, wfv_id, inputs):
    return filemodels.StoredFile.objects.filter(
        rawfile__datasetrawfile__dataset__id=dset_id, filetype='mzml')


# TODO make this method the standard for searches
def run_ipaw(job_id, dset_id, analysis_id, wfv_id, inputs, *dset_mzmls):
    """iPAW currently one dataset at a time, easy to join?
    2do: create lib datasets, make this code correct
    inputs is {'params': ['--isobaric', 'tmt10plex'],
               'singlefiles': {'--tdb': tdb_sf_id, ... }, #
               'mzml': ('--mzmls', os.path.join('{sdir}', '\\*.mzML')),}
    or shoudl inputs be DB things fields flag,sf_id (how for mzmls though?)
{'params': ['--isobaric', 'tmt10plex', '--instrument', 'qe', '-profile', 'slurm'], 'mzml': ('--mzmls', '{sdir}/*.mzML'), 'singlefiles': {'--tdb': 42659, '--dbsnp': 42665, '--genome': 42666, '--snpfa': 42662, '--cosmic': 42663, '--ddb': 42664, '--blastdb': 42661, '--knownproteins': 42408, '--gtf': 42658, '--mods': 42667}}
    """
    analysis = models.Analysis.objects.get(pk=analysis_id)
    nfwf = models.NextflowWfVersion.objects.select_related('nfworkflow').get(
        pk=wfv_id)
    stagefiles = {}
    for flag, sf_id in inputs['singlefiles'].items():
        sf = filemodels.StoredFile.objects.get(pk=sf_id)
        stagefiles[flag] = (sf.servershare.name, sf.path, sf.filename)
    mzmls = {'param': inputs['mzml'], 
             'files': [(x.servershare.name, x.path, x.filename) for x in
                       filemodels.StoredFile.objects.filter(pk__in=dset_mzmls)]}
    run = {'timestamp': datetime.strftime(analysis.date, '%Y%m%d_%H.%M'),
           'analysis_id': analysis.id,
           'wf_commit': nfwf.commit,
           'nxf_wf_fn': nfwf.filename,
           'repo': nfwf.nfworkflow.repo,
           'name': analysis.name,
           }
    create_nf_search_entries(analysis, nfwf, job_id)
    res = tasks.run_nextflow_ipaw.delay(run, inputs['params'], mzmls, stagefiles)
    Task.objects.create(asyncid=res.id, job_id=job_id, state='PENDING')


# FIXME need to store a datasetANalysis for keeping track.
# dset / analysis / job (with args)

def create_nf_search_entries(analysis, nfwf, job_id):
    try:
        nfs = models.NextflowSearch.objects.get(analysis=analysis)
    except models.NextflowSearch.DoesNotExist:
        nfs = models.NextflowSearch(nfworkflow=nfwf, job_id=job_id,
                                    analysis=analysis)
        nfs.save()
