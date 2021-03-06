from tapiriik.settings import PP_WEBSCR, PP_RECEIVER_ID, PAYMENT_CURRENCY
from tapiriik.auth import Payments, User
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.core.urlresolvers import reverse
import urllib.request
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

@csrf_exempt
def payments_ipn(req):
    raw_data = req.body.decode("utf-8")
    raw_data += "&cmd=_notify-validate"
    ipnreq = urllib.request.Request(PP_WEBSCR)
    ipnreq.add_header("Content-type", "application/x-www-form-urlencoded")
    result = urllib.request.urlopen(ipnreq, raw_data.encode("utf-8"))
    response = result.read().decode("utf-8")
    if response != "VERIFIED":
        logger.error("IPN request %s not validated - response %s" % (req.body, response))
        return HttpResponse(status=403)
    if req.POST["receiver_id"] != PP_RECEIVER_ID or req.POST["mc_currency"] != PAYMENT_CURRENCY:
        logger.error("IPN request %s has incorrect details" % req.POST )
        return HttpResponse(status=400)
    if req.POST["payment_status"] != "Completed":
        logger.error("IPN request %s not complete" % req.POST)
        return HttpResponse()
    logger.info("IPN request %s OK" % str(req.POST))
    payment = Payments.LogPayment(req.POST["txn_id"], amount=req.POST["mc_gross"], initialAssociatedAccount=req.POST["custom"], email=req.POST["payer_email"])
    user = User.Get(req.POST["custom"])
    User.AssociatePayment(user, payment)
    return HttpResponse()


def payments_return(req):
    if req.user is None or User.HasActivePayment(req.user):
        return redirect("/")
    return render(req, "payments/return.html")


def payments_claim(req):
    err = False
    if req.user is None:
        return redirect("/")
    if "email" in req.POST:
        if payments_claim_initiate(req, req.user, req.POST["email"]):
            return redirect("/")
        else:
            err = True
    return render(req, "payments/claim.html", {"err": err})

def payments_claim_ajax(req):
    if req.user is None or not payments_claim_initiate(req, req.user, req.POST["email"]):
        return HttpResponse(status=404)
    return HttpResponse()

def payments_claim_initiate(request, user, email):
    payment = Payments.GetPayment(email=email)
    if payment is None:
        return False
    claim_code = Payments.GenerateClaimCode(user, payment)
    reclaim_url = request.build_absolute_uri(reverse("payments_claim_return", kwargs={"code": claim_code}))
    from tapiriik.web.email import generate_message_from_template, send_email
    message, plaintext_message = generate_message_from_template("email/payment_reclaim.html", {"url":reclaim_url})
    send_email(email, "Reclaim your payment on tapiriik.com", message, plaintext_message=plaintext_message)
    return True

def payments_claim_wait_ajax(request):
    if request.user is None:
        return HttpResponse(status=404)
    return HttpResponse(json.dumps({"claimed": not Payments.HasOutstandingClaimCode(request.user)}), content_type="application/json")

def payments_claim_return(request, code):
    user, payment = Payments.ConsumeClaimCode(code)
    if not payment:
        return render(request, "payments/claim_return_fail.html")
    User.AssociatePayment(user, payment)
    User.Login(user, request)  # In case they somehow managed to log out - they've proved their identity.
    return redirect("/#/payments/claimed")
