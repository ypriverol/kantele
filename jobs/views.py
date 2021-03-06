import json
from datetime import datetime 

from celery import states
from django.http import (HttpResponseForbidden, HttpResponse,
                         HttpResponseNotAllowed, JsonResponse)
from django.contrib.auth.decorators import login_required
from jobs import models
from jobs.jobs import Jobstates, is_job_ready, create_file_job, get_job_ownership
from rawstatus.models import (RawFile, StoredFile, ServerShare,
                              SwestoreBackedupFile, Producer)
from analysis.models import AnalysisResultFile
from analysis.views import write_analysis_log
from dashboard import views as dashviews
from datasets import views as dsviews
from kantele import settings


def set_task_done(task_id):
    task = models.Task.objects.get(asyncid=task_id)
    task.state = states.SUCCESS
    task.save()


def taskclient_authorized(client_id, possible_ids):
    """Possibly use DB in future"""
    return client_id in possible_ids


def task_failed(request):
    if not request.method == 'POST':
        return HttpResponseNotAllowed(permitted_methods=['POST'])
    if 'client_id' not in request.POST or not taskclient_authorized(
            request.POST['client_id'], settings.CLIENT_APIKEYS):
        return HttpResponseForbidden()
    print('Failed task registered task id {}'.format(request.POST['task']))
    task = models.Task.objects.get(asyncid=request.POST['task'])
    task.state = states.FAILURE
    task.save()
    msg = request.POST['msg'] if 'msg' in request.POST else ''
    models.TaskError.objects.create(task_id=task.id, message=msg)
    return HttpResponse()


def update_storagepath_file(request):
    data = json.loads(request.body.decode('utf-8'))
    print('Updating storage task finished')
    if 'client_id' not in data or not taskclient_authorized(
            data['client_id'], [settings.STORAGECLIENT_APIKEY]):
        return HttpResponseForbidden()
    if 'fn_id' in data:
        sfile = StoredFile.objects.get(pk=data['fn_id'])
        sfile.servershare = ServerShare.objects.get(name=data['servershare'])
        sfile.path = data['dst_path']
        if 'newname' in data:
            sfile.filename = data['newname']
        sfile.save()
    elif 'fn_ids' in data:
        sfns = StoredFile.objects.filter(pk__in=[int(x) for x in data['fn_ids']])
        sfns.update(path=data['dst_path'])
    if 'task' in data:
        set_task_done(data['task'])
    return HttpResponse()


def set_md5(request):
    if 'client_id' not in request.POST or not taskclient_authorized(
            request.POST['client_id'], [settings.STORAGECLIENT_APIKEY]):
        return HttpResponseForbidden()
    storedfile = StoredFile.objects.get(pk=request.POST['sfid'])
    storedfile.md5 = request.POST['md5']
    storedfile.checked = request.POST['source_md5'] == request.POST['md5']
    storedfile.save()
    print('stored file saved')
    if 'task' in request.POST:
        set_task_done(request.POST['task'])
        print('MD5 saved')
    return HttpResponse()


@login_required
def delete_job(request, job_id):
    if request.method != 'POST':
        return HttpResponseNotAllowed(permitted_methods=['POST'])
    job = models.Job.objects.get(pk=job_id)
    ownership = get_job_ownership(job, request)
    if not ownership['owner_loggedin'] and not ownership['is_staff']:
        return HttpResponseForbidden()
    job.delete()
    return HttpResponse()



def delete_storedfile(request):
    data = request.POST
    if 'client_id' not in data or not taskclient_authorized(
            data['client_id'], [settings.STORAGECLIENT_APIKEY,
                                settings.SWESTORECLIENT_APIKEY]):
        return HttpResponseForbidden()
    sfile = StoredFile.objects.filter(pk=data['sfid']).select_related(
        'rawfile').get()
    if sfile.filetype == 'raw':
        sfile.rawfile.deleted = True
        sfile.rawfile.save()
    sfile.delete()
    if 'task' in data:
        set_task_done(data['task'])
    return HttpResponse()


def downloaded_px_file(request):
    """Storedfile and rawfn update proper md5 and set checked
    Creates job to add file to dset to move file to storage.
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(permitted_methods=['POST'])
    data = json.loads(request.body.decode('utf-8'))
    if 'client_id' not in data or not taskclient_authorized(
            data['client_id'], [settings.STORAGECLIENT_APIKEY]):
        return HttpResponseForbidden()
    dataset = {'dataset_id': data['dset_id'], 'removed_files': {},
               'added_files': {1: {'id': data['raw_id']}}}
    sf = StoredFile.objects.get(pk=data['sf_id']) 
    raw = RawFile.objects.get(pk=data['raw_id'])
    sf.md5 = data['md5']
    sf.checked = True
    raw.source_md5 = data['md5']
    sf.save()
    raw.save()
    dsviews.save_or_update_files(dataset)
    if 'task' in data:
        set_task_done(data['task'])
    return HttpResponse()


def created_swestore_backup(request):
    data = request.POST
    if 'client_id' not in data or not taskclient_authorized(
            data['client_id'], [settings.SWESTORECLIENT_APIKEY]):
        return HttpResponseForbidden()
    backup = SwestoreBackedupFile.objects.filter(storedfile_id=data['sfid'])
    backup.update(swestore_path=data['swestore_path'], success=True)
    if 'task' in request.POST:
        set_task_done(request.POST['task'])
    return HttpResponse()


def created_mzml(request):
    data = request.POST
    if 'client_id' not in data or not taskclient_authorized(
            data['client_id'], [settings.MZMLCLIENT_APIKEY]):
        return HttpResponseForbidden()
    storedfile = StoredFile.objects.get(pk=request.POST['sfid'])
    storedfile.filename = request.POST['filename']
    storedfile.save()
    if 'task' in data:
        set_task_done(data['task'])
    return HttpResponse()


def scp_mzml(request):
    data = request.POST
    if 'client_id' not in data or not taskclient_authorized(
            data['client_id'], [settings.MZMLCLIENT_APIKEY]):
        return HttpResponseForbidden()
    if 'task' in data:
        set_task_done(data['task'])
    return HttpResponse()


def analysis_run_done(request):
    if request.method == 'POST':
        data = json.loads(request.body.decode('utf-8'))
        if 'log' in data:
            write_analysis_log(data['log'], data['analysis_id'])
        if ('client_id' not in data or
                data['client_id'] not in settings.CLIENT_APIKEYS):
            return HttpResponseForbidden()
        if 'task' in data:
            set_task_done(data['task'])
        return HttpResponse()
    else:
        return HttpResponseNotAllowed(permitted_methods=['POST'])


def store_longitudinal_qc(request):
    if request.method == 'POST':
        data = json.loads(request.body.decode('utf-8'))
        if ('client_id' not in data or
                data['client_id'] not in settings.CLIENT_APIKEYS):
            return HttpResponseForbidden()
        elif data['state'] == 'error':
            dashviews.fail_longitudinal_qc(data)
        else:
            dashviews.store_longitudinal_qc(data)
        if 'task' in data:
            set_task_done(data['task'])
        return HttpResponse()
    else:
        return HttpResponseNotAllowed(permitted_methods=['POST'])


def store_analysis_result(request):
    """Stores the reporting of a transferred analysis result file,
    checks its md5"""
    if request.method != 'POST':
        return HttpResponseNotAllowed(permitted_methods=['POST'])
    data = request.POST
    # create analysis file
    if ('client_id' not in data or
            data['client_id'] != settings.ANALYSISCLIENT_APIKEY):
        return HttpResponseForbidden()
    # FIXME nextflow to file this, then poll rawstatus/md5success
    # before deleting rundir etc, or report taskfail
    # Reruns lead to trying to store files multiple times, avoid that:
    anashare = ServerShare.objects.get(name=settings.ANALYSISSHARENAME)
    try:
        sfile = StoredFile.objects.get(rawfile_id=data['fn_id'], filetype=data['ftype'])
    except StoredFile.DoesNotExist:
        print('New transfer registered, fn_id {}'.format(data['fn_id']))
        sfile = StoredFile(rawfile_id=data['fn_id'], filetype=data['ftype'], 
                           servershare=anashare, path=data['outdir'],
                           filename=data['filename'], md5='', checked=False)
        sfile.save()
        AnalysisResultFile.objects.create(analysis_id=data['analysis_id'], sfile=sfile)
    else:
        print('Analysis result already registered as transfer, client asks for new '
              'MD5 check after a possible rerun. Running MD5 check.')
    create_file_job('get_md5', sfile.id)
    return HttpResponse()
    

@login_required
def retry_job(request, job_id):
    if request.method != 'POST':
        return HttpResponseNotAllowed(permitted_methods=['POST'])
    force = True if request.user.is_staff else False
    job = models.Job.objects.get(pk=job_id)
    ownership = get_job_ownership(job, request)
    if not ownership['owner_loggedin'] and not ownership['is_staff']:
        return HttpResponseForbidden()
    do_retry_job(job, force)
    return HttpResponse()


def do_retry_job(job, force=False):
    tasks = models.Task.objects.filter(job=job)
    if not is_job_ready(job=job, tasks=tasks) and not force:
        print('Tasks not all ready yet, will not retry, try again later')
        return
    tasks.exclude(state=states.SUCCESS).delete()
    try:
        job.joberror.delete()
    except models.JobError.DoesNotExist:
        pass
    job.state = Jobstates.PENDING
    job.save()
