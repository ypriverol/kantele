import os
import shutil
from urllib.parse import urljoin

from django.urls import reverse
from celery import shared_task

from kantele import settings as config
from jobs.post import update_db, taskfail_update_db

# Updating stuff in tasks happens over the API, assume no DB is touched. This
# avoids setting up auth for DB


@shared_task(bind=True)
def convert_to_mzml(self, fn, fnpath, outfile, sf_id, servershare, reporturl, failurl):
    """This will run on remote in other repo (proteomics-tasks) so there is no
    need to be no code in here, the task is an empty shell with only the
    task name"""
    return True


@shared_task(bind=True)
def scp_storage(self, mzmlfile, rawfn_id, dsetdir, servershare, reporturl, failurl):
    """This will run on remote in other repo (proteomics-tasks) so there is no
    need to be no code in here, the task is an empty shell with only the
    task name"""
    return True


@shared_task(bind=True, queue=config.QUEUE_STORAGE)
def rename_storage_location(self, srcpath, dstpath, storedfn_ids):
    print('Renaming dataset storage {} to {}'.format(srcpath, dstpath))
    dsttree = config.STORAGESHARE
    for srcdir, dstdir in zip(srcpath.split(os.sep), dstpath.split(os.sep)):
        if srcdir != dstdir:
            try:
                shutil.move(os.path.join(dsttree, srcdir),
                            os.path.join(dsttree, dstdir))
            except Exception:
                taskfail_update_db(self.request.id)
                raise
        dsttree = os.path.join(dsttree, dstdir)
    postdata = {'fn_ids': storedfn_ids, 'dst_path': dstpath,
                'task': self.request.id, 'client_id': config.APIKEY}
    url = urljoin(config.KANTELEHOST, reverse('jobs:updatestorage'))
    try:
        update_db(url, postdata)
    except RuntimeError:
        # FIXME cannot move back shutil.move(dst, src)
        raise


@shared_task(bind=True, queue=config.QUEUE_STORAGE)
def move_file_storage(self, fn, srcshare, srcpath, dstpath, fn_id):
    src = os.path.join(config.SHAREMAP[srcshare], srcpath, fn)
    dst = os.path.join(config.STORAGESHARE, dstpath, fn)
    print('Moving file {} to {}'.format(src, dst))
    dstdir = os.path.split(dst)[0]
    if not os.path.exists(dstdir):
        try:
            os.makedirs(dstdir)
        except FileExistsError:
            # Race conditions may happen, dir already made by other task
            pass
        except Exception:
            taskfail_update_db(self.request.id)
            raise
    elif not os.path.isdir(dstdir):
        taskfail_update_db(self.request.id)
        raise RuntimeError('Directory {} is already on disk as a file name. '
                           'Not moving files.')
    try:
        shutil.move(src, dst)
    except Exception as e:
        taskfail_update_db(self.request.id)
        raise RuntimeError('Could not move file tot storage:', e)
    postdata = {'fn_id': fn_id, 'servershare': config.STORAGESHARENAME,
                'dst_path': dstpath, 'client_id': config.APIKEY,
                'task': self.request.id}
    url = urljoin(config.KANTELEHOST, reverse('jobs:updatestorage'))
    try:
        update_db(url, postdata)
    except RuntimeError:
        shutil.move(dst, src)
        raise
    print('File {} moved to {}'.format(fn_id, dst))


@shared_task(bind=True, queue=config.QUEUE_STORAGE)
def move_stored_file_tmp(self, fn, path, fn_id):
    src = os.path.join(config.STORAGESHARE, path, fn)
    dst = os.path.join(config.TMPSHARE, fn)
    print('Moving stored file {} to tmp'.format(fn_id))
    try:
        shutil.move(src, dst)
    except Exception:
        taskfail_update_db(self.request.id)
        raise
    postdata = {'fn_id': fn_id, 'servershare': config.TMPSHARENAME,
                'dst_path': '', 'client_id': config.APIKEY,
                'task': self.request.id}
    url = urljoin(config.KANTELEHOST, reverse('jobs:updatestorage'))
    try:
        update_db(url, postdata)
    except RuntimeError:
        shutil.move(dst, src)
        raise
    print('File {} moved to tmp and DB updated'.format(fn_id))
