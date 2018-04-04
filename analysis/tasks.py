import os
import json
import shutil
import subprocess
from urllib.parse import urljoin
from dulwich.porcelain import clone, reset, pull

from django.urls import reverse
from celery import shared_task

from jobs.post import update_db, taskfail_update_db
from kantele import settings
from analysis import qc, galaxy


def run_nextflow(run, params, rundir, gitwfdir):
    """Fairly generalized code for kantele celery task to run a WF in NXF"""
    print('Starting nextflow workflow {}'.format(run['nxf_wf_fn']))
    outdir = os.path.join(rundir, 'output')
    try:
        clone(run['repo'], gitwfdir, checkout=run['wf_commit'])
    except FileExistsError:
        pull(gitwfdir, run['repo'])
        reset(gitwfdir, 'hard', run['wf_commit'])
    # There will be files inside data dir of WF repo so we must be in
    # that dir for WF to find them
    subprocess.run(['nextflow', 'run', run['nxf_wf_fn'], *params,
                    '--outdir', outdir, '-with-trace', '-resume'], check=True,
                   stderr=subprocess.PIPE, stdout=subprocess.PIPE, cwd=gitwfdir)
    return rundir


def stage_files(stagedir, stagefiles, params=False):
    if not os.path.exists(stagedir):
        os.makedirs(stagedir)
    for flag, fdata in stagefiles.items():
        fpath = os.path.join(settings.SHAREMAP[fdata[0]], fdata[1], fdata[2])
        dst = os.path.join(stagedir, fdata[2])
        if not os.path.exists(dst):
            shutil.copy(fpath, dst)
        if params:
            params.extend([flag, dst])
    return params 


@shared_task(bind=True, queue=settings.QUEUE_NXF)
def run_nextflow_ipaw(self, run, params, mzmls, stagefiles):
    print('Got message to run iPAW workflow, preparing')
    postdata = {'client_id': settings.APIKEY,
                'analysis_id': run['analysis_id'], 'task': self.request.id}
    runname = 'ipaw_{}_{}_{}'.format(run['analysis_id'], run['name'], run['timestamp'])
    # FIXME temp fix, replace on run['name']
    rundir = os.path.join(settings.NEXTFLOW_RUNDIR, runname).replace(' ', '_')
    gitwfdir = os.path.join(rundir, 'gitwfs')
    if not os.path.exists(rundir):
        os.makedirs(rundir)
    stagedir = os.path.join(settings.ANALYSIS_STAGESHARE, runname)
    print('Staging files to {}'.format(stagedir))
    params = stage_files(stagedir, stagefiles, params)
    stage_files(stagedir, {x[2]: x for x in mzmls})
    with open(os.path.join(rundir, 'mzmldef.txt'), 'w') as fp:
        for fn in mzmls:
            fp.write('{fpath}\t{setn}\n'.format(fpath=os.path.join(stagedir, fn[2]), setn=fn[3]))
    params.extend(['--mzmldef', os.path.join(rundir, 'mzmldef.txt')])
    try:
        run_nextflow(run, params, rundir, gitwfdir)
    except subprocess.CalledProcessError as e:
        # FIXME report stderr with e
        errmsg = 'OUTPUT:\n{}\nERROR:\n{}'.format(e.stdout, e.stderr)
        taskfail_update_db(self.request.id, errmsg)
        raise RuntimeError('Error occurred running iPAW workflow '
                           '{}\n\nERROR MESSAGE:\n{}'.format(rundir, errmsg))
    outfiles = os.listdir(os.path.join(rundir, 'output'))
    outfiles = [os.path.join(rundir, 'output', x) for x in outfiles]
    postdata.update({'state': 'ok'})
    reporturl = urljoin(settings.KANTELEHOST, reverse('jobs:analysisdone'))
    report_finished_run(postdata, self.request.id, run['outdir'], rundir, outfiles)
    return run


@shared_task(bind=True, queue=settings.QUEUE_NXF)
def run_nextflow_longitude_qc(self, run, params, stagefiles):
    print('Got message to run QC workflow, preparing')
    reporturl = urljoin(settings.KANTELEHOST, reverse('jobs:storelongqc'))
    postdata = {'client_id': settings.APIKEY, 'rf_id': run['rf_id'],
                'analysis_id': run['analysis_id'], 'task': self.request.id}
    runname = 'longqc_{}_{}'.format(run['analysis_id'], run['timestamp'])
    rundir = os.path.join(settings.NEXTFLOW_RUNDIR, runname)
    gitwfdir = os.path.join(rundir, 'gitwfs')
    if not os.path.exists(rundir):
        os.makedirs(rundir)
    stagedir = os.path.join(rundir, 'stage')
    params = stage_files(stagedir, stagefiles, params)
    try:
        run_nextflow(run, params, rundir, gitwfdir)
    except subprocess.CalledProcessError:
        with open(os.path.join(gitwfdir, 'trace.txt')) as fp:
            header = next(fp).strip('\n').split('\t')
            exitfield, namefield = header.index('exit'), header.index('name')
            for line in fp:
                line = line.strip('\n').split('\t')
                if line[namefield] == 'createPSMPeptideTable' and line[exitfield] == '3':
                    postdata.update({'state': 'error', 'errmsg': 'Not enough PSM data found in file to extract QC from, possibly bad run'})
                    report_finished_run(reporturl, postdata, self.request.id, rundir)
                    raise RuntimeError('QC file did not contain enough quality PSMs')
        taskfail_update_db(self.request.id)
        raise RuntimeError('Error occurred running QC workflow '
                           '{}'.format(rundir))
    outfiles = os.listdir(os.path.join(rundir, 'output'))
    # TODO hardcoded is probably not a good idea
    qcfiles = {}
    expect_out = {'sqltable': 'mslookup_db.sqlite', 'psmtable': 'psmtable.txt',
                  'peptable': 'peptable.txt', 'prottable': 'prottable.txt'}
    if set(expect_out.values()).difference(outfiles):
        taskfail_update_db(self.request.id)
        raise RuntimeError('Ran QC workflow but output file {} not '
                           'found'.format(expfn))
    qcfiles = {x: os.path.join(rundir, 'output', fn) for x, fn 
               in expect_out.items()}
    qcreport = qc.calc_longitudinal_qc(qcfiles)
    postdata.update({'state': 'ok', 'plots': qcreport})
    report_finished_run(reporturl, postdata, self.request.id, 'internal_results', rundir,
                        qcfiles.values())
    return run


def report_finished_run(url, postdata, task_id, userdir, rundir, outfiles=False):
#    with open('report.json', 'w') as fp:
#        json.dump(postdata, fp)
    try:
        if outfiles:
            transfer_resultfiles(userdir, rundir, outfiles)
    except RuntimeError:
        taskfail_update_db(task_id)
        raise
    else:
        shutil.rmtree(rundir)
        update_db(url, json=postdata)


def transfer_resultfiles(userdir, rundir, outfiles):
    """Copies analysis results to data server"""
    # TODO need scp for this, including a firewall opening
    outdir = os.path.join(settings.SHAREMAP[settings.ANALYSISSHARENAME],
                          userdir, os.path.split(rundir)[-1])
    if not os.path.exists(outdir):
        os.makedirs(outdir)
    for fn in outfiles:
        shutil.copy(fn, os.path.join(outdir, os.path.basename(fn)))
