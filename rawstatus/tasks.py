import hashlib
import os
import requests
import subprocess
from ftplib import FTP
from urllib.parse import urljoin
from time import sleep
from datetime import datetime

from django.urls import reverse

from kantele import settings as config
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from jobs.post import update_db, taskfail_update_db


def calc_md5(fnpath):
    hash_md5 = hashlib.md5()
    with open(fnpath, 'rb') as fp:
        for chunk in iter(lambda: fp.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


@shared_task(queue=config.QUEUE_PXDOWNLOAD, bind=True)
def download_px_file_raw(self, ftpurl, ftpnetloc, sf_id, raw_id, size, sharename, dset_id):
    """Downloads PX file, validate by file size, get MD5
    Uses separate queue on storage, because otherwise trouble when 
    needing the storage queue while downloading PX massive dsets.
    """
    print('Downloading PX dataset rawfile {}'.format(ftpurl))
    postdata = {'client_id': config.APIKEY, 'task': self.request.id,
                'sf_id': sf_id, 'raw_id': raw_id, 'dset_id': dset_id}
    fn = os.path.split(ftpurl)[1]
    dstfile = os.path.join(config.SHAREMAP[sharename], fn)
    try:
        with FTP(ftpnetloc) as ftp:
            ftp.login()
            ftp.retrbinary('RETR {}'.format(ftpurl), 
                           open(dstfile, 'wb').write)
    except Exception:
        taskfail_update_db(self.request.id)
        raise
    if os.path.getsize(dstfile) != size:
        print('Size of fn {} is not the same as source size {}'.format(dstfile, size))
        taskfail_update_db(self.request.id)
    try:
        postdata['md5'] = calc_md5(dstfile)
    except Exception:
        taskfail_update_db(self.request.id)
        raise
    url = urljoin(config.KANTELEHOST, reverse('jobs:downloadpx'))
    try:
        update_db(url, json=postdata)
    except RuntimeError:
        try:
            self.retry(countdown=60)
        except MaxRetriesExceededError:
            update_db(url, postdata)
            raise
    print('MD5 of {} is {}, registered in DB'.format(dstfile, postdata['md5']))


@shared_task(queue=config.QUEUE_STORAGE, bind=True)
def get_md5(self, source_md5, sfid, fnpath, servershare):
    # This should be run on the storage server
    print('MD5 requested for file {}'.format(sfid))
    fnpath = os.path.join(config.SHAREMAP[servershare], fnpath)
    try:
        result = calc_md5(fnpath)
    except Exception:
        taskfail_update_db(self.request.id)
        raise
    postdata = {'sfid': sfid, 'md5': result, 'client_id': config.APIKEY,
                'task': self.request.id, 'source_md5': source_md5}
    url = urljoin(config.KANTELEHOST, reverse('jobs:setmd5'))
    msg = ('Could not update database: http/connection error {}. '
           'Retrying in one minute')
    try:
        update_db(url, postdata, msg)
    except RuntimeError:
        try:
            self.retry(countdown=60)
        except MaxRetriesExceededError:
            update_db(url, postdata, msg)
            raise
    print('MD5 of {} is {}, registered in DB'.format(fnpath, result))
    return result


@shared_task(bind=True, queue=config.QUEUE_STORAGE)
def delete_file(self, servershare, filepath, fn_id):
    fileloc = os.path.join(config.SHAREMAP[servershare], filepath)
    try:
        os.remove(fileloc)
    except FileNotFoundError:
        # File is already deleted or just not where it is, pass for now,
        # will be registered as deleted
        pass
    except Exception:
        taskfail_update_db(self.request.id)
        raise
    msg = ('Could not update database with deletion of fn {} :'
           '{}'.format(filepath, '{}'))
    url = urljoin(config.KANTELEHOST, reverse('jobs:deletefile'))
    postdata = {'sfid': fn_id, 'task': self.request.id,
                'client_id': config.APIKEY}
    try:
        update_db(url, postdata, msg)
    except RuntimeError:
        try:
            self.retry(countdown=60)
        except MaxRetriesExceededError:
            update_db(url, postdata, msg)
            raise


@shared_task(bind=True, queue=config.QUEUE_SWESTORE)
def swestore_upload(self, md5, servershare, filepath, fn_id):
    print('Uploading file {} to swestore'.format(filepath))
    fileloc = os.path.join(config.SHAREMAP[servershare], filepath)
    uri = os.path.join(config.SWESTORE_URI, md5)
    mountpath_fn = os.path.join(config.DAV_PATH, md5)
    # Check if proj folder exists on the /mnt/dav, mkdir if not
    # Dont upload using /mnt/dav, use curl
    curl = ['curl', '-1', '--location', 
            '--cert',  '{}:{}'.format(config.CERTLOC, config.CERTPASS),
            '--key', config.CERTKEYLOC, '-T', fileloc, uri]
    try:
        subprocess.check_call(curl)
    except Exception:
        taskfail_update_db(self.request.id)
        raise
    # if the upload is REALLY quick sometimes the DAV hasnt refreshed and you
    # will get filenotfound
    sleep(5)
    try:
        md5_upl = calc_md5(mountpath_fn)
    except FileNotFoundError:
        # could indicate no transfer, or dav not mounted
        # user needs to investigate and retry this
        print('Failed to get MD5 for Swestore upload of '
              '{}'.format(filepath))
        taskfail_update_db(self.request.id)
        raise
    else:
        if not md5_upl == md5:
            print('Swestore upload failed with incorrect MD5, retrying')
            taskfail_update_db(self.request.id)
            raise
        else:
            print('Successfully uploaded {} '
                  'with MD5 {}'.format(mountpath_fn, md5_upl))
    postdata = {'sfid': fn_id, 'swestore_path': uri,
                'task': self.request.id, 'client_id': config.APIKEY}
    url = urljoin(config.KANTELEHOST, reverse('jobs:createswestore'))
    msg = ('Could not update database with for fn {} with swestore URI {} :'
           '{}'.format(filepath, uri, '{}'))
    try:
        update_db(url, postdata, msg)
    except RuntimeError:
        try:
            self.retry(countdown=60)
        except MaxRetriesExceededError:
            update_db(url, postdata, msg)
            raise
