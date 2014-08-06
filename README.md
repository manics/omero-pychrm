omero-wndcharm
==============

Scripts for using Wndcharm in `OMERO http://www.openmicroscopy.org/`.

This requires the `WND-CHARM Python API
https://github.com/wnd-charm/wnd-charm/` to be installed. You may wish to
create and enter a virtualenv before doing so. WND-CHARM can be installed from
source, or using pip:

    pip install git+https://github.com/wnd-charm/wnd-charm.git

Although OmeroWndcharm can be installed using pip:

    pip install git+git://github.com/manics/omero-pychrm.git

The scripts for using WND-CHARM in OMERO are also in the same Github source
repository so you still need to clone it:

    git clone https://github.com/manics/omero-pychrm.git
    cd omero-pychrm
    python setup.py install

Copy the scripts into the OMERO.server script directory:

    cp -r scripts OMERO_SERVER/lib/scripts/wnd-charm
