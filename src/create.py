import os
import zipfile
from crx3_pb2 import SignedData, CrxFileHeader
import struct
import io
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, utils, padding

fileBufferLength = 4096


def create_publickey(private_key):
    public_key = private_key.public_key()
    data = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return data


def get_zipped_data_and_basename_from_dir(_dir):
    if os.path.isdir(_dir):
        return zipdir(_dir), _dir
    else:
        raise IOError('Source is not a directory or zip file <%s>' % _dir)


def package(_dir, output):
    zipdata, basename = get_zipped_data_and_basename_from_dir(_dir)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    public_key = create_publickey(private_key)

    signed_header_data_str = create_signed_header_data_str(public_key)

    signed = sign(signed_header_data_str, zipdata, private_key)
    header_str = create_header_str(public_key, signed, signed_header_data_str)

    save_crx_file(header_str, zipdata, output, basename)


def sign(signed_header_data_str, zipped, private_key):
    signed_header_size_octets = struct.pack('<I', len(signed_header_data_str))

    chosen_hash = hashes.SHA256()
    hasher = hashes.Hash(chosen_hash, default_backend())
    hasher.update(b'CRX3 SignedData\00')
    hasher.update(signed_header_size_octets)
    hasher.update(signed_header_data_str)

    for i in range(0, len(zipped), fileBufferLength):
        if i + fileBufferLength <= len(zipped):
            hasher.update(zipped[i: i + fileBufferLength])
        else:
            hasher.update(zipped[i: len(zipped)])

    digest = hasher.finalize()

    return private_key.sign(digest, padding.PKCS1v15(), utils.Prehashed(chosen_hash))


def zipdir(directory, inject=None):
    zip_memory = io.BytesIO()
    with zipfile.ZipFile(zip_memory, 'w', zipfile.ZIP_DEFLATED) as zf:

        def _rec_zip(path, parent='', _inject=None):
            if _inject:
                for fname, fdata in _inject.items():
                    zf.writestr(fname, fdata)

            for d in os.listdir(path):
                child = os.path.join(path, d)
                name = '%s/%s' % (parent, d)
                if os.path.isfile(child):
                    zf.write(child, name)
                if os.path.isdir(child):
                    _rec_zip(child, name)

        _rec_zip(directory, _inject=inject)
        zf.close()
        zipdata = zip_memory.getvalue()
        return zipdata


def get_crx_id(public_key):
    digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
    digest.update(public_key)
    hased = digest.finalize()
    return hased[0:16]


def create_signed_header_data_str(public_key):
    signed_header_data = SignedData()
    signed_header_data.crx_id = get_crx_id(public_key)
    return signed_header_data.SerializeToString()


def create_header_str(public_key, signed, signed_header_data_str):
    header = CrxFileHeader()
    proof = header.sha256_with_rsa.add()
    proof.public_key = public_key
    proof.signature = signed
    header.signed_header_data = signed_header_data_str
    return header.SerializeToString()


def save_crx_file(header_str, zipped, path, crdx):
    header_size_octets = struct.pack('<I', len(header_str))

    fileLocation = path if path else '%s.crx' % crdx
    with open(fileLocation, 'wb') as crx:
        data = [b'Cr24', struct.pack('<I', 3), header_size_octets, header_str, zipped]
        for d in data:
            crx.write(d)


def create(path_extension: str, path_save: str = ''):
    return package(path_extension, path_save)
