"""Talk to the bot in the terminal, no WhatsApp needed:  python whatsapp_bot/simulate.py"""
import flow

session = flow.new_session()
print("(type messages as the resident; Ctrl-C to quit)\n")
while True:
    reply, session, action = flow.handle(session, input("you> "))
    print(f"bot> {reply}" + (f"\n[{action}: {session.get('rating')}]" if action else "") + "\n")
