# WhatsApp "rate my area" bot

A small web service that answers WhatsApp messages with a four-question survey and stores the answers in Supabase.
The dashboard's **Area Ratings** page reads them. The conversation logic is in `flow.py` and needs no network:
`python whatsapp_bot/simulate.py` lets you try it by typing.

## What it stores

Never a phone number. A salted SHA-256 hash of the number is kept, which is enough to allow one answer a week per person
and to delete their answers when they send **STOP**. The rest is: ISO week, area name, the issue named, a 1 to 5 rating and the language.

## One-time setup

1. **Supabase:** run `supabase/area_ratings.sql` in the dashboard project's SQL editor.
2. **Meta:** at developers.facebook.com create an app, add the **WhatsApp** product, and note the *temporary token* (for testing),
   the *Phone number ID*, and the app's *App secret* (Settings, Basic). For real use, add a permanent system-user token and a
   phone number of your own; Meta's free tier covers the first 1,000 service conversations a month.
3. **Host the bot** (Render, Railway or Fly free tiers all work). Start command: `gunicorn app:app`, root directory `whatsapp_bot`.
   Set these environment variables:

   | Variable | What |
   |---|---|
   | `WHATSAPP_TOKEN` | Meta access token |
   | `WHATSAPP_PHONE_NUMBER_ID` | the sending number's ID |
   | `WHATSAPP_VERIFY_TOKEN` | any long random text you make up |
   | `WHATSAPP_APP_SECRET` | the app secret (used to check that calls really come from Meta) |
   | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | the dashboard's project |
   | `PHONE_HASH_SALT` | any long random text; keep it, since changing it makes people count as new |

4. **Webhook:** in Meta's WhatsApp settings set the callback URL to `https://<your host>/webhook`, the verify token to the value
   above, and subscribe to the **messages** field.
5. Add `WHATSAPP_BOT_NUMBER = "91XXXXXXXXXX"` to the dashboard's secrets to show the share link on the Area Ratings page.

## Rules to keep to

- Only reply to people who message first. WhatsApp allows free-form replies for 24 hours after a person's message; do not send
  unprompted broadcasts from this bot.
- Keep the first message's consent wording and the STOP option.
- Do not link answers to a person, a voter list or a phone number.
