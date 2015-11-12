#
# this is the test fabfile
#
#

from fabric.api import *
src_rc = "/root/openrc"

def test():
    vols = local(". %s ; cinder list |grep -v ID|awk '{print $2}'" % src_rc,capture=True)
    for vol in vols:
        show_out = local(". %s ; cinder show %s" % (src_rc, vol), capture=True)
        print show_out


