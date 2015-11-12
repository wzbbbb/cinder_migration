from fabric.api import *
src_rc = "/home/zw451w/openrc_src"
dst_rc = "/home/zw451w/openrc_dst"
# the base directory where every
src_vol_dir = "/mnt/cinder-volumes"
dst_vol_dir = "/var/lib/cinder/mnt" #local
user='zw451w'
key="/home/zw451w/.ssh/id_rsa"
remote_controller="135.21.85.117"

maps_vol=[]
maps_snap=[]
# find all remote NFS backends
remote_dirs = local("ssh -i %s %s@%s ls %s " %  (key, user, remote_controller, src_vol_dir), capture=True)
# find all local NFS backends
local_dirs = local("ls %s " %  dst_vol_dir, capture=True)

# collect volumes info in SRC
def info_vol():
    volumes = local(". %s ; cinder list |grep -v ID|awk '{print $2}'" % src_rc,capture=True)
    vols = volumes.split('\n')
    for vol in vols:
        dic={}
        show_output = local(". %s ; cinder show %s" % (src_rc, vol), capture=True)
        show_out = show_output.split('\n')
        for out in show_out:
            if ' status' in out:
                sta = out.split('|')[2].strip()
        if  sta == 'available' or sta == 'in-use':
            for out in show_out:
                if 'attachments' in out:
                    atta = out.split('|')[2].strip()
                    if atta != '[]':
                        dev = atta.split("{")[1].split(",")[0].split(":")[1].split("'")[1]
                        inst = atta.split("{")[1].split(",")[1].split(":")[1].split("'")[1]
                        inst_name = local(". %s ; nova show %s|grep ' name'|cut -f3 -d'|'|sed 's/^ *//g'|sed 's/ *$//g'" % (src_rc, inst), capture=True)
                        dic['device'] = dev
                        dic['inst_id'] = inst
                        dic['inst_name'] = inst_name
                if ' size' in out:
                    siz = out.split('|')[2].strip()
                if ' display_name' in out:
                    disp_name = out.split('|')[2].strip()
            dic['volume_id'] = vol
            dic['size'] = siz
            dic['disp_name'] = disp_name
            dic['status'] = sta
        maps_vol.append(dic)

# collect volume snapshot info in SRC
def info_snap():
    snapshots = local(". %s ; cinder snapshot-list |grep -v ID|grep -v '+'" % src_rc,capture=True)
    snaps = snapshots.split('\n')
    for snap in snaps:
        dic={}
        sta = snap.split('|')[3].strip()
        if  sta == 'available' or sta == 'in-use':
            dic['snap_id'] = snap.split('|')[1].strip()
            dic['volume_id'] = snap.split('|')[2].strip()
            dic['status'] = sta
            dic['disp_name'] = snap.split('|')[4].strip()
            dic['size'] = snap.split('|')[5].strip()
        maps_snap.append(dic)
    for mas in maps_snap:
        for mav in maps_vol:
            if mas['volume_id'] == mav['volume_id']:
                mas['new_vol'] = mav['new_vol']
                break


# create new volumes in DST
def create_vol():
    for ma in maps_vol:
        if ma:
            new_vol = local(". %s ;cinder create --display-name %s %s|grep ' id'|awk '{print $4}' " % (dst_rc, ma['disp_name'], ma['size']), capture=True)
            ma['new_vol'] = new_vol
            print "=== Created volume" , ma['new_vol']
    print maps_vol

# create new snapshot in DST
def create_snap():
    existing_vol = local(". %s ; cinder list |grep -v ID|awk '{print $2}'" % dst_rc,capture=True)
    dst_vol = existing_vol.split('\n')
    for ma in maps_snap:
        if ma and ma['new_vol'] in dst_vol: # make sure the volume exist in DST
            new_snap = local(". %s ;cinder snapshot-create --display-name %s %s|grep ' id'|awk '{print $4}' " % (dst_rc, ma['disp_name'], ma['new_vol']), capture=True)
            ma['new_snap'] = new_snap
            print "=== Created snapshot" , ma['new_snap']
    print maps_snap

# copy volume to DST
def copy_vol():
    for ma in maps_vol:
        if ma:
            print "=== Trying" , ma['volume_id']
            for remote_dir in remote_dirs.split():  # find the correct directory
                rc = local("ssh -i %s %s@%s ls %s/%s/volume-%s ; echo $?" %  (key, user, remote_controller, src_vol_dir,remote_dir,ma['volume_id']), capture=True)
                if len(rc) > 1 : # rc should contain full dir and 0
                    remote_volume=src_vol_dir + '/' + remote_dir + '/volume-' + ma['volume_id']
                    break
            for local_dir in local_dirs.split(): # find the first backend with enough space
                sizeK = local("df -k %s/%s|grep -v Filesystem|awk '{print $4}'" % (dst_vol_dir,local_dir), capture=True )
                sizeG = int(sizeK) / 1000000
                if sizeG > int(ma['size']):
                    local_volume = dst_vol_dir + '/' + local_dir + '/volume-' + ma['new_vol']
                    break
            src_cksum = local("ssh -i %s %s@%s md5sum %s |awk '{print $1}'" % (key, user, remote_controller, remote_volume) , capture=True)
            local("rsync -avz -e 'ssh -i %s' %s@%s:%s %s" % (key, user, remote_controller, remote_volume,local_volume))
            dst_cksum = local("md5sum %s|awk '{print $1}'" % local_volume , capture=True)
            if src_cksum != dst_cksum:
                exit(1)
            else:
                print "=== Volume" , ma['volume_id'], "migrated!"

# copy snapshots to DST
def copy_snap():
    for ma in maps_snap:
        if ma:
            print "=== Trying" , ma['snap_id']
            for remote_dir in remote_dirs.split():  # find the correct directory
                rc = local("ssh -i %s %s@%s ls %s/%s/snapshot-%s ; echo $?" %  (key, user, remote_controller, src_vol_dir,remote_dir,ma['snap_id']), capture=True)
                if len(rc) > 1 : # rc should contain full dir and 0
                    remote_snap=src_vol_dir + '/' + remote_dir + '/snapshot-' + ma['snap_id']
                    break
            for local_dir in local_dirs.split(): # find the first backend with enough space
                sizeK = local("df -k %s/%s|grep -v Filesystem|awk '{print $4}'" % (dst_vol_dir,local_dir), capture=True )
                sizeG = int(sizeK) / 1000000
                if sizeG > int(ma['size']):
                    local_snap = dst_vol_dir + '/' + local_dir + '/snap-' + ma['new_snap']
                    break
            src_cksum = local("ssh -i %s %s@%s md5sum %s |awk '{print $1}'" % (key, user, remote_controller, remote_snap) , capture=True)
            local("rsync -avz -e 'ssh -i %s' %s@%s:%s %s" % (key, user, remote_controller, remote_snap,local_snap))
            dst_cksum = local("md5sum %s|awk '{print $1}'" % local_snap , capture=True)
            if src_cksum != dst_cksum:
                exit(1)
            else:
                print "=== Snap" , ma['snap_id'], "migrated!"
# attach them to running instances
def attach_vol():
    for ma in maps_vol:
        if 'inst_name' in ma.keys():
            print "=== Attaching volume", ma['new_vol'], "to", ma['inst_name']
            local(". %s; nova volume-attach %s %s %s" % (dst_rc, ma['inst_name'], ma['new_vol'], ma['device']))
            print "=== "

def quota_migrate():
    src_tenant_id = local(". ./openrc_src; env|grep OS_TENANT_ID|cut -f2 -d'='", capture=True)
    dst_tenant_id = local(". ./openrc_dst; env|grep OS_TENANT_ID|cut -f2 -d'='", capture=True)
    src_quo = local(". ./openrc_src; cinder quota-show %s|grep -v ' -1'|grep -v 'Value'|grep -v '+'" % src_tenant_id, capture=True )
    for quo in src_quo.split("\n"):
        prop = quo.split('|')[1].strip()
        val = quo.split('|')[2].strip()
        local(". ./openrc_dst; cinder quota-update %s --%s %s" % (dst_tenant_id,prop,val), capture=True)

    print "=== Quota migration done!"


def migrate():
    print "=== Checking volumes in SRC"
    print "=== "
    info_vol()
    print "=== Creating new volumes in DST"
    print "=== "
    create_vol()
    print "=== Copying volumes to DST"
    print "=== "
    copy_vol()
    print "=== Attaching volumes to instance in DST"
    print "=== "
    attach_vol()
    print "=== Migrating quotas to DST"
    print "=== "
    quota_migrate()
    print "=== Checking snapshot in SRC"
    print "=== "
    info_snap()
    print "=== Creating snapshots in DST"
    print "=== "
    create_snap()
    print "=== Copying snapshots to DST"
    print "=== "
    copy_snap()
