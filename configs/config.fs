# Vendor AIDs. AOSP only reserves 2900-2999 for the vendor partition and defines
# none of these, but the stock image ships them in /vendor/etc/passwd and
# /vendor/etc/group, and init files name them: init.qcom.rc chowns the coresight
# nodes to vendor_qdss. Without a definition in the build's AID database,
# host_init_verifier stops with "Unable to decode GID for 'vendor_qdss'".
#
# The numbers are the stock ones (vendor_qti_diag 2901 ... vendor_thales_weaver
# 2914, no gaps); keep them in step with those two blobs.

[AID_VENDOR_QTI_DIAG]
value: 2901

[AID_VENDOR_QDSS]
value: 2902

[AID_VENDOR_RFS]
value: 2903

[AID_VENDOR_RFS_SHARED]
value: 2904

[AID_VENDOR_ADPL_ODL]
value: 2905

[AID_VENDOR_QRTR]
value: 2906

[AID_VENDOR_THERMAL]
value: 2907

[AID_VENDOR_FASTRPC]
value: 2908

[AID_VENDOR_QTR]
value: 2909

[AID_VENDOR_NXP_STRONGBOX]
value: 2910

[AID_VENDOR_NXP_WEAVER]
value: 2911

[AID_VENDOR_SSGTZD]
value: 2912

[AID_VENDOR_THALES_STRONGBOX]
value: 2913

[AID_VENDOR_THALES_WEAVER]
value: 2914
