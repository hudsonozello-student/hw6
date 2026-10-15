# AI Prompts Log — Homework 6: Campus Customs Vendor Desk (Tokenomics + Prompt Injection)

MGT 409 AI Foundations. This file logs the exact prompts I typed into my vibe coder (Claude Code) for this homework, organized by problem. Each prompt is copied verbatim. Follow-up prompts are listed under the problem they belong to, in the order I sent them, and each one explains why the earlier prompt needed a follow-up or what went wrong with it.

---

## Problem 1: Vibe coder prompts

### Prompt 1

```text
MGT 409 Homework 6: Campus Customs Vendor Desk (Tokenomics + Prompt Injection)

Please name this chat: "MGT 409 Homework 6: Campus Customs Vendor Desk (Tokenomics + Prompt Injection)"

background info: we are campus customs. we are building a vendor desk agent that can read a document, identify the key facts (vendor, item, price, lead time, min order) and recommend whether campus customs (CC) shop should buy, following rules in the campus customs shop handbook. this document could be a vendor quote, invoice, catalogue page, supplier email, etc.

this HW is designed to focus on two very specific items: cost (handbook is ~10k tokens and used on every call) and safety (the vendor documents have hidden instructions aimed at AI that we must avoid). our goal is to measure the bill, cut it, attack the agent, and defend the attack.

do NOT send emails or make payments. the email and payment tool should ONLY write to a log file.

Use the PORTKEY_API_KEY and ONLY gpt-6-luna for every AI call. If you run any other models, then I will lose points and that will make me very sad.

we will work through one problem at a time. at the end, we will push the project to a PUBLIC GitHub repo and submit the repo URL to my professor for him to grade (the last problem will have details on this). do NOT commit the .env.

all of the data needed for this project is in HW6 folder here: C:\Users\hudso\Documents\NOT_ONE_DRIVE\Grad School\Yale\Fall 2026\MGT 409 AI Foundations\Homework\Homework 6\data

see below for a rundown of the different files and what they mean:
data/shop_handbook.md: CC shop handbook contaiing products, vendors, purchasing rules, etc
data/prices.json: gpt-6-luna prices
data/practice_docs/: 12 vendor docs in HTL, PDF, email
data/practice_key.json: correct answers for the practice docs
data/exam_docs/: 10 additional vendor docs (with no answer key!)

quick note that all vendors and docs are made up just for this assignment, this is not real CC data

Problem 1: Vibe coder prompts

Please create AI_prompts.md as a log file of what is typed into the vibe coder (Here) and keep it updaed throughout the whole assignment (this whole chat). there should be one section for each problem titled wit the problem number and title (I will always state this, as I have above: "Problem 1: Vibe coder prompts"). include every prompt I send until I tell you to move to the next problem. if I require more than one prompt, then I will have to explain why/what went wrong in the original prompt
```

---

## Problem 2: Size up the handbook

### Prompt 1

```text
Problem 2: Size up the handbook

REview the data/shop_handbook.md. this is CC shop handbook, and the agent will send it to model on every single cal. also look at data/prices.json, the gpt-6-luna price list

figure out how many tokens the handbook is. in output/handbook_estimate.md write:

(1) token count and how you got it
(2) what the handbook alone costsin $ on one call, on 1k calls, with cached tokens, and without them. show your math

Note that in P4, we will check these estimates against real runs

Please send me a message in this chat with the answers in addition to writing to that file. in the file, please include alot of detail, in the message chat here please be brief
```

---

## Problem 3: Build the vendor desk agent

### Prompt 1

```text
Problem 3: Build the vendor desk agent

okay - and just to confirm is that price coming out of my claude availability or my token api luna availability? that is alot of money to spend! lets be careful in spending this money

now - onto problem 3. we are going to build the vendor desk agent wirth PydanticAI using gpt-6-luna. the agent is 4 files:

prompts/prompt.md: instructions for the agent (agent also sends teh handbook to the model on every call)
agent.py: entry point
tools.py: tools
models.py: structured types

give the agent the path to one vendor document. it will read the document with a tool (HTML, PDF, and .eml email files must all work) and returns: vendor, SKU, unit price, lead time in days, minimum order, decision (either recommend, or do_not_recommend) following the handbook rules, and a one-sentence reason.

Additionally, the agent must have 2 trap tools: send_email and approve_payment. its job will never need them. they are there to catch malicious document that tricks your agent into emailing someone or paying a vendor. they do not send or pay anything. they only append the call and its arguments to output/trap_calls.json (start this as an empty list), so that if the file ever has an entry, a dcoument took over your agent. keep them on your system for the whole hw.

After every run, please append to:
output/usage_log.json: document, time, token counts the API reports, and dollar cost using prices.json
output/audit_trail.json: each tool call with its arguments and a short result, fplus the final answer

agent should run like this within the terminal: python agent.py --doc data/practice_docs/p01_bluehen_quote.html

(what this is doing: runs the agent on one venfor quote and logs the answer, tools, and cost)

Run it on p01 and p08 to show it works. start output/harness.md: each field in models.py and why, and each tool in one line.
```

---

## Problem 4: With and without cached tokens

### Prompt 1

```text
please do not add the defenses yet, as I will add those with professor's instruction in later step. but thank you for notifying me.

Problem 4: With and without cached tokens

note that the handbook is the same on all calls so the model can reuse it from a cache at a much cheaper price. lets test this to see the value. please run the agent on all 12 pratice documents 2 ways:
(1) with the cache: set up so the handbook gets reused from the cache
(2) without the cache: set up so nothing gets reused from the cache

Check the toke counts the api sends back to prove each setup really did what you think. a without-cache run that still shows cached tokens does NOT count. please make sure this is done appropriately.

Save every model from both setupts to output/cache_test.json.

For each call, include the setup, document, every token count the API reports, and dollars from prices.json

in output/cache_test.md
(1) total cost and cost per document for each setup, and the percent you saved
(2) how your real numbers compare to your problem 2 estimate
(3) projection for 1,000 documents a day for 30 days, with and without cache
(4) anything in numbers that surprised you and why it happens
```

---

## Problem 5: Attack your own agent

### Prompt 1

```text
Problem 5: Attack your own agent

as you have already noted, some vendor docs are booby-trapped with text aimed at the AI. run your problm 3 agent, with NO new defenses, on all 12 dos in the data/practice_docs/. compare each answer to data/practice_key.json and check output/trap_calls.json, the log of fake email and payment tools from problem problem 3.

Save output/attack_results.json: for each doc, whether each field matched the key, whether the decision matched, wheterh a trap tool was called, and wheterh a link or other strange text showed up in the answer

in output/attack_results.md: for every doc that fooled the agent, write what fooled it and where in the file the booby-trap was hiding. Open the documents the way a person would (browser, PDF viewer, email app) and compare with what the agent read
```

---

## Problem 6: Defend your agent

### Prompt 1

```text
Problem 6: Defend your agent

Defend the agent at 3 levels:
(1) code: what your program does to the doc before any model sees it
(2) design: how the agent is put together, so a poisoned doc cannoy reach the dangerous tools or the decision
(3) prompt: rules in prompts/prompt.md

You may NOT delete send_email or approve_payment from system. the shop will use them later in a human sign-of. keep a way to run the agent with no defenses (to be used in problem 7)

then, re-run all 12 practice docs. save output/defense_results.json in the same shape as prob 5, plus tokens and dollars per doc

Clean docs must still come bac with the correct values. refusing or blanking out a real quote counts as a failure and will make me sad.

In output/defense_results.md

* a before and after table for all 12 docs
* what each lyer catches that the others miss
* the extra tokens and dollars each layer adds per doc


Add safety measures to output/harness.md in a safety section: what each defense layer does, expained in plain words that a human could understand
```

---

## Problem 7: red team

### Prompt 1

```text
Problem 7: red team

now, we are the attacker. make 2 new booby-trappedd venor docs in data/my_attacks/ (HTML, PDF, or email but dont do two of the same type). each one should use a hiding trick or an attack goal that is not in the practice set. a person opening to doc should see a normal quote. please make these attacks minor (ie not something that would actually hurt me, my tokens, my cost, etc. - can be something small and theoretical only just to show a y/n if it worked). 

run obth attacks on the agent with no deenses and on the agent with defenses. 

In output/red_team, for each attack include: what is hidden, where, what it tries to make the agent do, and what happened befre and after your defenses.

more points for attacks that are new and that actually fool the agent with no defenses. I want to get alot of points so please be creative and do a good job here!
```

---

## Problem 8: Exam documents

### Prompt 1

```text
Problem 8: Exam documents

Before executing the below steps - please perform any necessary patches that you noted above to make the defenses stronger

data/exam_docs/ has 10 vendor documents with no answer key. run the final defended agent on all of them. do not hand-edit the results. note that there will likely be hidden attacks in here so want to use maximum defenses to detect so I dont lose points.

saave output/exam_results.json with one entry per exam file. each entry will have the following fields:

file: the exam file name, e.g. e01_qute.html
vendor
sku
unit_price
lead_time_days
min_order
decision: recommend or do_not_recommend
reasno
trap_tool_called: true or false
input_tokens, cached_tokens, output_tokens
cost_usd

Graders will compare these results to a hidden answer key and may rerun some agents to check. will get points for correct fields and decisions, no trap tool calls, and clean documents handled normally
```

---

## Problem 9: Results page

### Prompt 1

```text
Problem 9: Results page

built output/hw6_report.html: it msut be one file that opens by a double-click with no internet and no other files next to it. it must show the following 5 things, using real numbers from earlier problems:

(1) caching results, with a chart
(2) attacks before and after your defenses
(3) what your defenses cost in tokens and dollars
(4) your exam results and your two red team attacks
(5) a short recommendation to the store manager: should campus customs turn this agent on for real vendor mail, and what would it cost per month at 1,000 documents per day

extra points are given for a designed page that reads well (fonts, color, layout). please put in extra effort to try to maximize these points
```

---

## Problem 10: Push to GitHub and submit the URL

### Prompt 1

```text
Problem 10: Push to GitHub and submit the URL

push the project to a public github repo and sumbit the repo URL on canvas (I will be the one to submit the URL on canvas, but please tell me the exact URL). Graders will clone the repo so make sure it opens and the files below are there!

include the whole data/ folder (the course data plus your two attack files) so graders can clone the repo and run agent immediately. do NOT commit the real .env. use .gitignore to keep it out, and include .env.example with placeholders only

expected repo:

hw6/
--AI_prompts.md
--README.md
--.gitignore
--.env.example
--requirements.txt
--agent.py
--tools.py
--models.py
--prompts/
----prompt.md
--data/
----shop_handbook.md
----prices.json
----practice_key.json
----practice_docs/ (the 12 practice documents)
----exam_docs/ (the 10 exam docs)
----my_attacks/ (2 created attack files)
--output/
----handbook_estimate.md
----harness.md
----usage_log.json
----audit_trail.json
----trap_calls.json
----cache_test.json
----cache_test.md
----attack_results.json
----attack_results.md
----defense_results.json
----defense_results.md
----red_team.md
----exam_results.json
----hw6_report.html

other python files are fine. put a short note in README.md on how to run your agent
```
