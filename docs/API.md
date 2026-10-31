# API reference

129 operations. Generated from the running application by `backend/scripts/export_openapi.py`; the full machine-readable contract is [`openapi.json`](openapi.json). Interactive docs are at `/docs` on a running API.

**Conventions.** Everything is JSON under `/api`. Authentication is an `HttpOnly` session cookie; state-changing requests must come from the app's own origin. Errors always look like `{"error": {"code", "message", "field?", "request_id?"}}`; branch on `code`, never on `message`. Money is in rupees with `currency: "INR"`; calculators return `calculation_id`, `formula_version`, `assumptions` and `missing`. Every response carries `X-Request-ID`.

**Auth column.** *public* operations are the explicit allow-list in `app/public_routes.py` (each with its justification); everything else needs a signed-in session and only ever touches the caller's own objects.

## ai

| Method | Path | What it does | Auth |
|---|---|---|---|
| POST | `/api/ai/chat` | Chat | session |
| GET | `/api/ai/conversations/latest` | Latest | session |
| POST | `/api/ai/conversations/{cid}/transcript` | Transcript | session |
| GET | `/api/ai/faqs` | Questions answered locally before any generative-AI call | session |
| POST | `/api/ai/session-token` | Session Token | session |
| GET | `/api/ai/status` | Status | session |
| POST | `/api/ai/tools/{name}` | Executes a tool requested by the Live voice model so numbers still come from deterministic code | session |

## auth

| Method | Path | What it does | Auth |
|---|---|---|---|
| POST | `/api/auth/account/delete` | Permanently delete the account and all of its data. Needs the password (sample workspaces have none) | session |
| POST | `/api/auth/email-verification/confirm` | Confirm Email Verification | public |
| POST | `/api/auth/email-verification/request` | Request Email Verification | session |
| POST | `/api/auth/login` | Login | public |
| POST | `/api/auth/logout` | Logout | public |
| GET | `/api/auth/me` | Me | session |
| POST | `/api/auth/password` | Change the password (current password required). Every other session is signed out; this one stays | session |
| POST | `/api/auth/password-reset/confirm` | Reset Confirm | public |
| POST | `/api/auth/password-reset/request` | Always answers the same way whether or not the email has an account (no account enumeration) | public |
| GET | `/api/auth/password-reset/status` | Whether this server can send reset emails (shown on the login page before the user types anything) | public |
| POST | `/api/auth/signup` | Signup | public |

## cards

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/cards` | List Cards | session |
| POST | `/api/cards` | Add Card | session |
| POST | `/api/cards/best-for-spend` | Best | session |
| GET | `/api/cards/catalogue` | Catalogue | session |
| GET | `/api/cards/explore` | Sample new-card discovery; spending relevance is not issuer eligibility or approval | session |
| GET | `/api/cards/insights/categories` | Where a different existing card may earn more, based on spending categories (RD §13.3) | session |
| PATCH | `/api/cards/{card_id}` | Update Card | session |
| DELETE | `/api/cards/{card_id}` | Delete Card | session |
| GET | `/api/cards/{card_id}/benefits` | Benefits | session |
| POST | `/api/cards/{card_id}/import-document` | Import Card Document | session |
| GET | `/api/cards/{card_id}/spend-reconciliation` | Preview which confirmed statement purchases would count toward this card's reward estimate | session |
| POST | `/api/cards/{card_id}/spend-reconciliation` | Apply Spend | session |
| DELETE | `/api/cards/{card_id}/spend-reconciliation` | Undo Spend | session |

## consultations

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/consultations` | List Requests | session |
| POST | `/api/consultations` | Request Call | session |
| POST | `/api/consultations/preview` | Preview | session |
| GET | `/api/consultations/{cid}` | Get Request | session |
| POST | `/api/consultations/{cid}/cancel` | Cancel | session |
| POST | `/api/consultations/{cid}/retry` | Retry | session |

## dashboard

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/dashboard` | Dashboard | session |

## demo

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/demo/fixtures` | Downloadable sample files so the upload flow itself can be demonstrated | public |
| GET | `/api/demo/fixtures/{name}` | Get Fixture | public |
| POST | `/api/demo/workspace` | Create Workspace | public |

## documents

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/documents` | List Documents | session |
| POST | `/api/documents` | Upload | session |
| GET | `/api/documents/{doc_id}` | Get Document | session |
| DELETE | `/api/documents/{doc_id}` | Delete Document | session |
| GET | `/api/documents/{doc_id}/facts` | Get Facts | session |
| PATCH | `/api/documents/{doc_id}/facts/{fact_id}` | Correct Fact | session |
| POST | `/api/documents/{doc_id}/facts/{fact_id}/reject` | The user says this value is wrong or doesn't apply. It stays visible as rejected and is never used | session |
| GET | `/api/documents/{doc_id}/file` | Download | session |
| GET | `/api/documents/{doc_id}/receipt` | Receipt Detail | session |
| POST | `/api/documents/{doc_id}/receipt/link` | Receipt Link | session |
| POST | `/api/documents/{doc_id}/reprocess` | Reprocess | session |
| POST | `/api/documents/{doc_id}/search` | Search Document | session |

## emis

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/emis` | List Emis | session |
| POST | `/api/emis` | Add Emi | session |
| GET | `/api/emis/calendar` | Calendar View | session |
| POST | `/api/emis/explore` | Compare contemplated EMI options side by side with affordability (RD §14.4, HW 'comparisons, hidden charges') | session |
| PATCH | `/api/emis/{emi_id}` | Update Emi | session |
| DELETE | `/api/emis/{emi_id}` | Removing a detected EMI marks its recurring group as 'not an EMI' so it isn't re-detected | session |
| POST | `/api/emis/{emi_id}/confirm` | Confirm Emi | session |
| POST | `/api/emis/{emi_id}/what-if` | Emi What If | session |

## family

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/family` | List Members | session |
| POST | `/api/family` | Add Member | session |
| PATCH | `/api/family/{member_id}` | Update Member | session |
| DELETE | `/api/family/{member_id}` | Delete Member | session |

## goals

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/goals` | List Goals | session |
| POST | `/api/goals` | Create Goal | session |
| PATCH | `/api/goals/{goal_id}` | Update Goal | session |
| DELETE | `/api/goals/{goal_id}` | Delete Goal | session |
| POST | `/api/goals/{goal_id}/contributions` | Add Contribution | session |
| DELETE | `/api/goals/{goal_id}/contributions/{cid}` | Delete Contribution | session |

## insights

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/forecast` | Get Forecast | session |
| POST | `/api/forecast/exclusions` | Set Exclusion | session |
| POST | `/api/forecast/expected` | Add Expected | session |
| DELETE | `/api/forecast/expected/{item_id}` | Delete Expected | session |
| PUT | `/api/forecast/opening-balance` | Set Opening | session |
| GET | `/api/insights/spending` | Spending | session |
| POST | `/api/insights/subscriptions/{group_id}` | Decide Subscription | session |
| POST | `/api/insights/unusual/{txn_id}` | Decide Unusual | session |
| GET | `/api/transactions/{txn_id}/explain` | Explain | session |

## insurance

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/insurance/catalogue` | Catalogue | session |
| POST | `/api/insurance/compare` | Compare | session |
| POST | `/api/insurance/emergency` | Emergency | session |
| GET | `/api/insurance/events` | Events | session |
| GET | `/api/insurance/overview` | Overview | session |
| GET | `/api/insurance/policies` | List Policies | session |
| GET | `/api/insurance/policies/{pid}` | Policy Detail | session |
| POST | `/api/insurance/policies/{pid}/confirm` | Confirm Policy | session |
| PUT | `/api/insurance/policies/{pid}/members` | Set Members | session |
| POST | `/api/insurance/recommend` | Recommend | session |

## loans

| Method | Path | What it does | Auth |
|---|---|---|---|
| POST | `/api/loans/calculate` | Calculate | session |
| GET | `/api/loans/catalogue` | Catalogue | session |
| POST | `/api/loans/compare` | Compare | session |
| GET | `/api/loans/documents` | Loan Documents | session |
| GET | `/api/loans/documents/{doc_id}` | Loan at a glance + Real Cost from extracted terms + clauses with sources (RD §12.9) | session |
| GET | `/api/loans/products/{product_id}` | Product | session |
| POST | `/api/loans/recommend` | Recommend | session |

## notifications

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/notifications` | List Notifications | session |
| POST | `/api/notifications/read-all` | Read All | session |
| POST | `/api/notifications/{nid}/read` | Mark Read | session |

## onboarding

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/accounts` | List Accounts | session |
| POST | `/api/accounts` | Add Account | session |
| DELETE | `/api/accounts/{account_id}` | Delete Account | session |
| GET | `/api/consents` | List Consents | session |
| POST | `/api/consents` | Grant | session |
| DELETE | `/api/consents/{purpose}` | Revoke | session |
| PATCH | `/api/onboarding/about` | Update About | session |
| POST | `/api/onboarding/phone/verification` | Start Phone Verification | session |
| POST | `/api/onboarding/phone/verification/check` | Check Phone Verification | session |
| POST | `/api/onboarding/step` | Set Step | session |

## ops

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/ready` | Can this instance serve traffic? Database reachable and schema at the code's head revision | public |

## other

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/health` | Health | public |

## profile

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/profile` | Get Profile | session |
| POST | `/api/profile/delete-all` | User-visible delete control (RD §23.1): removes every uploaded file and all profile data; keeps the login | session |
| GET | `/api/profile/export` | Download everything we hold about the signed-in user as JSON (data portability, RD §23.1) | session |
| PATCH | `/api/profile/overrides` | Set Override | session |
| POST | `/api/profile/recurring/{group_id}` | Recurring Action | session |
| GET | `/api/profile/review` | Review | session |
| GET | `/api/profile/spending` | Spending | session |
| GET | `/api/transactions` | List Transactions | session |
| PATCH | `/api/transactions/{txn_id}` | Patch Transaction | session |

## reminders

| Method | Path | What it does | Auth |
|---|---|---|---|
| GET | `/api/reminders` | List Reminders | session |
| PUT | `/api/reminders/items/{kind}/{object_id}` | Switch reminders off (or back on) for one EMI, card or policy | session |
| PUT | `/api/reminders/preferences` | Update Prefs | session |
| POST | `/api/reminders/send-now` | Send one reminder immediately (demo of the reminder flow, RD §30 step 40) | session |
| DELETE | `/api/reminders/{reminder_id}` | Cancel a single upcoming reminder. It stays cancelled; other dates for the same item are unaffected | session |

## webhooks

| Method | Path | What it does | Auth |
|---|---|---|---|
| POST | `/api/webhooks/twilio` | Twilio Status | public |
| GET | `/api/webhooks/whatsapp` | Subscription handshake (Meta). Echo ``hub.challenge`` only if the verify token matches | public |
| POST | `/api/webhooks/whatsapp` | Whatsapp Webhook | public |

