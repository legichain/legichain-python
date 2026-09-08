"""Python SDK serializes explicit V2 calls without silently changing V1."""
import httpx
import pytest
from legichain import client as sdk


def receipt(request):
    return httpx.Response(202 if request.method=='POST' else 200,json={'operation_id':'tr_operation','status':'queued','status_url':'/v2/operations/tr_operation','protocol':1})


def test_sync_sdk_explicit_receipt_replay_and_v1_separation():
    seen=[]
    def handler(request):
        seen.append(request)
        if len(seen)==1:raise httpx.ReadTimeout('Synthetic response loss')
        return receipt(request)
    client=sdk.Legichain('synthetic.key',base_url='https://api.example')
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        client._client=transport
        with pytest.raises(httpx.ReadTimeout):client.enqueue_screen('person',{'name':'Synthetic'},idem='stable-key')
        result=client.enqueue_screen('person',{'name':'Synthetic'},idem='stable-key')
        assert result['status']=='queued'
        assert len(seen)==2 and seen[0].content==seen[1].content
        assert all(x.headers['Idempotency-Key']=='stable-key' for x in seen)
        client.enqueue_kyc_evidence('tr_app','nfc',{'access_error':'synthetic'},idem='nfc-key',client_token='synthetic-client')
        assert seen[-1].headers['X-KYC-Client-Token']=='synthetic-client'
        client.enqueue_report('wallet',{'address':'synthetic','format':'pdf'},idem='report')
        client.enqueue_kyc_report('tr_app',{'decision_id':'synthetic'},idem='kyc-report')
        client.enqueue_address_submit('tr_av',idem='av')
        client.operation('tr_op')
        client.operation_task('tr_op','task')
        client.operations(cursor='tr_cursor',state='failed',limit=25)
        assert seen[-1].url.params['limit']=='25'
        client.cancel_operation('tr_op')
        client.screen_person(name='Synthetic')
        assert seen[-1].url.path=='/v1/screen/person'
        count=len(seen)
        with pytest.raises(ValueError):client.enqueue_screen('person',{},idem='')
        with pytest.raises(ValueError):client.enqueue_screen('../reports',{},idem='key')
        assert len(seen)==count


@pytest.mark.asyncio
async def test_async_sdk_forwards_idempotency_and_queries():
    seen=[]
    def handler(request):seen.append(request);return receipt(request)
    client=sdk.AsyncLegichain('synthetic.key',region='tr')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client._client=transport
        result=await client.enqueue_screen('batch',{'items':[]},idem='stable-key')
        assert result['status']=='queued' and seen[-1].url.host=='tr-api.legichain.com'
        await client.enqueue_kyc_evidence('tr_app','liveness',{'frame_b64':'synthetic'},idem='key',client_token='token')
        assert seen[-1].headers['X-KYC-Client-Token']=='token'
        await client.enqueue_report('person',{'name':'Synthetic'},idem='report')
        await client.enqueue_kyc_report('tr_app',{},idem='kyc-report')
        await client.enqueue_address_submit('tr_av',idem='av')
        await client.operation('tr_op')
        await client.operation_task('tr_op','task')
        await client.operations(limit=10)
        await client.cancel_operation('tr_op')
        assert seen[-1].url.path=='/v2/operations/tr_op/cancel'
        with pytest.raises(ValueError):await client.enqueue_screen('person',{},idem='ı'*129)
