from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import botocore

try:
    from urllib.parse import urlparse
    from urllib.parse import urlunparse
    from urllib.parse import quote
    from urllib.parse import unquote
except ImportError:
    from urlparse import urlparse
    from urlparse import urlunparse
    from urllib import quote
    from urllib import unquote

import os
import time
import sys
from .utils import printTransferProgress
from multiprocessing import Value

class S3ClientWrapper:

    # These methods are static because in our use case, we always have the bucket and
    # endpoint and usually only call the download/upload once so there is no need to instantiate multiple objects

    @staticmethod
    def _check_import_boto3():
        """
        Check if pysftp is installed and give instructions if not.
        """
        try:
            import boto3
        except ImportError as e1:
            sys.stderr.write(
                ("\n\nLibraries required for client authenticated S3 access are not installed!\n"
                 "The Synapse client uses boto3 in order to access S3-like storage "
                 "locations.\n"
                 "To install this library:\n"
                 "    pip install boto3\n\n"
                 "If additional privileges are required on Unix-based systems such as Linux distributions or Mac OSX:"
                 "    (sudo) pip install boto3\n\n"
                 "On Windows, right click the Command Prompt(cmd.exe) and select 'Run as administrator' then:"
                 "    pip install boto3\n\n"
                 "\n\n\n"))
            raise

    @staticmethod
    def _create_progress_callback_func(file_size, filename, prefix=None):
        bytes_transferred= Value('d', 0)
        t0 = time.time()
        def progress_callback(bytes):
            with bytes_transferred.get_lock():
                bytes_transferred.value += bytes
                printTransferProgress(bytes_transferred.value, file_size, prefix=prefix, postfix=filename,
                                                     dt=time.time() - t0, previouslyTransferred=0)
        return progress_callback

    @classmethod
    def download_file(cls, bucket, endpoint_url, remote_file_key, download_file_path, profile_name = None, show_progress=True):
        cls._check_import_boto3()
        import boto3

        boto_session = boto3.session.Session(profile_name=profile_name)
        s3 = boto_session.resource('s3', endpoint_url=endpoint_url)

        try:
            s3_obj = s3.Object(bucket, remote_file_key)

            progress_callback = None
            if show_progress:
                s3_obj.load()
                file_size = s3_obj.content_length
                filename = os.path.basename(download_file_path)
                progress_callback = cls._create_progress_callback_func(file_size, filename, prefix='Downloading')
            s3_obj.download_file(download_file_path, Callback=progress_callback)
            return download_file_path
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == "404":
                raise ValueError("The key:%s does not exist in bucket:%s.", remote_file_key, bucket)
            else:
                raise


    @classmethod
    def upload_file(cls, bucket, endpoint_url, remote_file_key, upload_file_path, profile_name = None, show_progress=True):
        cls._check_import_boto3()
        import boto3

        if not os.path.isfile(upload_file_path):
            raise ValueError("The path: [%s] does not exist or is not a file", upload_file_path)

        boto_session = boto3.session.Session(profile_name=profile_name)
        s3 = boto_session.resource('s3', endpoint_url=endpoint_url)

        progress_callback = None
        if show_progress:
            file_size = os.stat(upload_file_path).st_size
            filename = os.path.basename(upload_file_path)
            progress_callback = cls._create_progress_callback_func(file_size, filename, prefix='Uploading')

        s3.Bucket(bucket).upload_file(upload_file_path, remote_file_key, Callback=progress_callback) #automatically determines whether to perform multi-part upload
        return upload_file_path


class SFTPWrapper:

    @staticmethod
    def _check_import_sftp():
        """
        Check if pysftp is installed and give instructions if not.
        """
        try:
            import pysftp
        except ImportError as e1:
            sys.stderr.write(
                ("\n\nLibraries required for SFTP are not installed!\n"
                 "The Synapse client uses pysftp in order to access SFTP storage "
                 "locations.  This library in turn depends on pycrypto.\n"
                 "To install these libraries on Unix variants including OS X, make "
                 "sure the python devel libraries are installed, then:\n"
                 "    (sudo) pip install pysftp\n\n"
                 "For Windows systems without a C/C++ compiler, install the appropriate "
                 "binary distribution of pycrypto from:\n"
                 "    http://www.voidspace.org.uk/python/modules.shtml#pycrypto\n\n"
                 "For more information, see: http://docs.synapse.org/python/sftp.html"
                 "\n\n\n"))
            raise

    @staticmethod
    def _parse_for_sftp(url):
        parsedURL = urlparse(url)
        if parsedURL.scheme!='sftp':
            raise(NotImplementedError("This method only supports sftp URLs of the "
                                      " form sftp://..."))
        return parsedURL


    @classmethod
    def upload_file(cls, filepath, url, username=None, password=None):
        """
        Performs upload of a local file to an sftp server.

        :param filepath: The file to be uploaded

        :param url: URL where file will be deposited. Should include path and protocol. e.g.
                    sftp://sftp.example.com/path/to/file/store

        :param username: username on sftp server

        :param password: password for authentication on the sftp server

        :returns: A URL where file is stored
        """
        cls._check_import_sftp()
        import pysftp

        parsedURL = cls._parse_for_sftp(url)

        with pysftp.Connection(parsedURL.hostname, username=username, password=password) as sftp:
            sftp.makedirs(parsedURL.path)
            with sftp.cd(parsedURL.path):
                sftp.put(filepath, preserve_mtime=True, callback=printTransferProgress)

        path = quote(parsedURL.path+'/'+os.path.split(filepath)[-1])
        parsedURL = parsedURL._replace(path=path)
        return urlunparse(parsedURL)

    @classmethod
    def download_file(cls, url, localFilepath=None, username=None, password=None):
        """
        Performs download of a file from an sftp server.

        :param url: URL where file will be deposited.  Path will be chopped out.
        :param localFilepath: location where to store file
        :param username: username on server
        :param password: password for authentication on  server

        :returns: localFilePath

        """
        cls._check_import_sftp()
        import pysftp

        parsedURL = cls._parse_for_sftp(url)

        #Create the local file path if it doesn't exist
        path = unquote(parsedURL.path)
        if localFilepath is None:
            localFilepath = os.getcwd()
        if os.path.isdir(localFilepath):
            localFilepath = os.path.join(localFilepath, path.split('/')[-1])
        #Check and create the directory
        dir = os.path.dirname(localFilepath)
        if not os.path.exists(dir):
            os.makedirs(dir)

        #Download file
        with pysftp.Connection(parsedURL.hostname, username=username, password=password) as sftp:
            sftp.get(path, localFilepath, preserve_mtime=True, callback=printTransferProgress)
        return localFilepath
