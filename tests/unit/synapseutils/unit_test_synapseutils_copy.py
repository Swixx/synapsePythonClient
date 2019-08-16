from nose.tools import assert_raises, assert_equal
from mock import patch, call
import synapseutils
from synapseutils.copy import *
from synapseutils.copy import _copy_file_handles_batch
from synapseutils.copy import _create_batch_file_handle_copy_request
from tests import unit


def setup(module):
    module.syn = unit.syn

def test_copyWiki_empty_Wiki():
    entity = {"id": "syn123"}
    with patch.object(syn, "getWikiHeaders", return_value=None), \
            patch.object(syn, "get", return_value=entity):
        synapseutils.copyWiki(syn, "syn123", "syn456", updateLinks=False)

def test_copyWiki_input_validation():
    to_copy=[{'id': '8688', 'title': 'A Test Wiki'},
             {'id': '8689', 'title': 'A sub-wiki', 'parentId': '8688'},
             {'id': '8690', 'title': 'A sub-sub-wiki', 'parentId': '8689'}]
    wiki={"id": "8786",
          "title": "A Test Wiki",
          "markdown": "some text"
         }
    entity={"id":"syn123"}
    expected_calls=[call({'id': 'syn123'}, '4'),
                    call({'id': 'syn123'}, '8688'),
                    call({'id': 'syn123'}, '8689'),
                    call({'id': 'syn123'}, '8690')]
    with patch.object(syn, "getWikiHeaders", return_value=to_copy),\
            patch.object(syn, "get", return_value=entity),\
            patch.object(syn, "getWiki", return_value=wiki) as mock_getWiki,\
            patch.object(syn, "store", return_value=wiki):
        synapseutils.copyWiki(syn, "syn123", "syn456", entitySubPageId="8688", destinationSubPageId="4",
                              updateLinks=False)
        mock_getWiki.assert_has_calls(expected_calls)

        synapseutils.copyWiki(syn, "syn123", "syn456", entitySubPageId=8688.0, destinationSubPageId=4.0,
                              updateLinks=False)
        mock_getWiki.assert_has_calls(expected_calls)

        assert_raises(ValueError, synapseutils.copyWiki, syn, "syn123", "syn456", entitySubPageId="some_string",
                              updateLinks=False)


class TestCopyFileHandles:

    def setup(self):
        self.patch_restPOST = patch.object(syn, 'restPOST')
        self.mock_restPOST = self.patch_restPOST.start()

    def teardown(self):
        self.patch_restPOST.stop()

    def test_copy_invalid_input_required_params(self):
        file_handles = ["test"]
        obj_types = []
        obj_ids = ["123"]
        return_val = None
        with patch.object(syn, "restPOST", return_value=return_val) as mocked_POST:
            assert_raises(ValueError, synapseutils.copyFileHandles, syn, file_handles, obj_types, obj_ids)
            mocked_POST.assert_not_called()

    def test_copy_invalid_input_optional_params(self):
        file_handles = ["test1", "test2"]
        obj_types = ["FileEntity", "FileEntity"]
        obj_ids = ["123", "456"]
        con_types = ["too", "many", "args"]
        file_names = ["too_few_args"]
        return_val = None
        with patch.object(syn, "restPOST", return_value=return_val) as mocked_POST:
            assert_raises(ValueError, synapseutils.copyFileHandles, syn, file_handles, obj_types, obj_ids,
                          con_types, file_names)
            mocked_POST.assert_not_called()

    def test_private_copy_batch(self):
        file_handles = ["123", "456"]
        obj_types = ["FileEntity", "FileEntity"]
        obj_ids = ["321", "645"]
        con_types = [None, "text/plain"]
        file_names = [None, "test"]
        expected_input = {
            "copyRequests": [
                {
                    "originalFile": {
                        "fileHandleId": "123",
                        "associateObjectId": "321",
                        "associateObjectType": "FileEntity"
                    },
                    "newContentType": None,
                    "newFileName": None
                },
                {
                    "originalFile": {
                        "fileHandleId": "456",
                        "associateObjectId": "645",
                        "associateObjectType": "FileEntity"
                    },
                    "newContentType": "text/plain",
                    "newFileName": "test"
                }
            ]
        }
        return_val = [
            {
                "newFileHandle": {
                    "contentMd5": "alpha_num_1",
                    "bucketName": "bucket.sagebase.org",
                    "fileName": "Name1.txt",
                    "createdBy": "111",
                    "contentSize": 16,
                    "concreteType": "type1",
                    "etag": "etag1",
                    "id": "123",
                    "storageLocationId": 1,
                    "createdOn": "2019-07-24T21:49:40.615Z",
                    "contentType": "text/plain",
                    "key": "key1"
                },
                "originalFileHandleId": "122"
            },
            {
                "newFileHandle": {
                    "contentMd5": "alpha_num2",
                    "bucketName": "bucket.sagebase.org",
                    "fileName": "Name2.txt",
                    "createdBy": "111",
                    "contentSize": 5,
                    "concreteType": "type2",
                    "etag": "etag2",
                    "id": "456",
                    "storageLocationId": 1,
                    "createdOn": "2019-07-24T21:49:40.638Z",
                    "contentType": "text/plain",
                    "key": "key2"
                },
                "originalFileHandleId": "124"
            }
        ]
        post_return_val = {"copyResults": return_val}
        with patch.object(syn, "restPOST", return_value=post_return_val) as mocked_POST:
            result = _copy_file_handles_batch(syn, file_handles, obj_types, obj_ids, con_types, file_names)
            assert_equal(result, post_return_val)
            mocked_POST.assert_called_once_with('/filehandles/copy', body=json.dumps(expected_input),
                                                endpoint=syn.fileHandleEndpoint)

    def test_copy_file_handles_multiple_batch(self):
        num_copies = 102
        file_handles = [str(x) for x in range(num_copies)]
        obj_types = ["FileEntity"] * num_copies
        obj_ids = [str(x) for x in range(num_copies)]
        con_types = ["text/plain"] * num_copies
        file_names = ["test" + str(i) for i in range(num_copies)]

        # expected returns
        return_val_1 = [{
                          "newFileHandle": {
                            "key": "value",
                          },
                          "originalFileHandleId": file_handle
                        } for file_handle in file_handles[:MAX_FILE_HANDLE_PER_COPY_REQUEST]]
        return_val_2 = [{
                          "newFileHandle": {
                            "key": "value",
                          },
                          "originalFileHandleId": file_handle
                        } for file_handle in file_handles[MAX_FILE_HANDLE_PER_COPY_REQUEST
                                                          :MAX_FILE_HANDLE_PER_COPY_REQUEST * 2]]
        post_return_val_1 = {"copyResults": return_val_1}
        post_return_val_2 = {"copyResults": return_val_2}
        expected_return = return_val_1 + return_val_2
        with patch.object(synapseutils.copy, "_copy_file_handles_batch",
                          side_effect=[post_return_val_1, post_return_val_2]) as mocked_private_copy:
            result = synapseutils.copyFileHandles(syn, file_handles, obj_types, obj_ids, con_types, file_names)
            mocked_private_copy.assert_any_call(syn, file_handles[:MAX_FILE_HANDLE_PER_COPY_REQUEST],
                                                obj_types[:MAX_FILE_HANDLE_PER_COPY_REQUEST],
                                                obj_ids[:MAX_FILE_HANDLE_PER_COPY_REQUEST],
                                                con_types[:MAX_FILE_HANDLE_PER_COPY_REQUEST],
                                                file_names[:MAX_FILE_HANDLE_PER_COPY_REQUEST])
            mocked_private_copy.assert_any_call(syn, file_handles[MAX_FILE_HANDLE_PER_COPY_REQUEST
                                                                  :MAX_FILE_HANDLE_PER_COPY_REQUEST * 2],
                                                obj_types[MAX_FILE_HANDLE_PER_COPY_REQUEST
                                                          :MAX_FILE_HANDLE_PER_COPY_REQUEST * 2],
                                                obj_ids[MAX_FILE_HANDLE_PER_COPY_REQUEST
                                                        :MAX_FILE_HANDLE_PER_COPY_REQUEST * 2],
                                                con_types[MAX_FILE_HANDLE_PER_COPY_REQUEST
                                                          :MAX_FILE_HANDLE_PER_COPY_REQUEST * 2],
                                                file_names[MAX_FILE_HANDLE_PER_COPY_REQUEST
                                                           :MAX_FILE_HANDLE_PER_COPY_REQUEST * 2])
            assert_equal(result, expected_return)
            assert_equal(mocked_private_copy.call_count, 2)

    def test_mixed_result_response(self):
        file_handles = ["789", "NotAccessibleFile"]
        obj_types = ["FileEntity", "FileEntity"]
        obj_ids = ["0987", "2352"]
        con_types = [None, "text/plain"]
        file_names = [None, "testName"]

        expected_input = {
            "copyRequests": [
                {
                    "originalFile": {
                        "fileHandleId": "789",
                        "associateObjectId": "0987",
                        "associateObjectType": "FileEntity"
                    },
                    "newContentType": None,
                    "newFileName": None
                },
                {
                    "originalFile": {
                        "fileHandleId": "NotAccessibleFile",
                        "associateObjectId": "2352",
                        "associateObjectType": "FileEntity"
                    },
                    "newContentType": "text/plain",
                    "newFileName": "testName"
                }
            ]
        }

        return_val = [
            {
                "newFileHandle": {
                    "contentMd5": "alpha_num_1",
                    "bucketName": "bucket.sagebase.org",
                    "fileName": "Name1.txt",
                    "createdBy": "111",
                    "contentSize": 16,
                    "concreteType": "type1",
                    "etag": "etag1",
                    "id": "0987",
                    "storageLocationId": 1,
                    "createdOn": "2019-07-24T21:49:40.615Z",
                    "contentType": "text/plain",
                    "key": "key1"
                },
                "originalFileHandleId": "789"
            },
            {
                "failureCode": "UNAUTHORIZED",
                "originalFileHandleId": "NotAccessibleFile"
            }
        ]

        post_return_val = {"copyResults": return_val}
        with patch.object(syn, "restPOST", return_value=post_return_val) as mocked_POST:
            result = synapseutils.copyFileHandles(syn, file_handles, obj_types, obj_ids, con_types, file_names)
            assert_equal(result, return_val)
            mocked_POST.assert_called_once_with('/filehandles/copy', body=json.dumps(expected_input),
                                                endpoint=syn.fileHandleEndpoint)

    def test_private_json_creator(self):
        file_handle_ids = ["345", "789"]
        obj_types = ["FileEntity", "FileEntity"]
        obj_ids = ["543", "987"]
        new_con_types = [None, "text/plain"]
        new_file_names = [None, "test"]
        expected_result = {
                            "copyRequests": [
                                {
                                    "originalFile": {
                                        "fileHandleId": "345",
                                        "associateObjectId": "543",
                                        "associateObjectType": "FileEntity"
                                    },
                                    "newFileName": None,
                                    "newContentType": None
                                },
                                {
                                    "originalFile": {
                                        "fileHandleId": "789",
                                        "associateObjectId": "987",
                                        "associateObjectType": "FileEntity"
                                    },
                                    "newFileName": "test",
                                    "newContentType": "text/plain"
                                }
                            ]
                        }
        result = synapseutils._create_batch_file_handle_copy_request(file_handle_ids, obj_types, obj_ids, new_con_types,
                                                                     new_file_names)
        assert_equal(expected_result, result)
