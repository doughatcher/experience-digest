---
title: "Adobe Patches Commerce Zero-Day Exploited Since Sept. 4"
date: 2026-09-09
draft: false
tags:
  - adobe-commerce
  - magento
  - cve
  - security
  - stylesmuggler
  - cve-2026-75650
  - apsb26-146
  - apsb26-138
  - zero-day
  - rce
  - template-injection
  - incident-response
  - patch-management
  - cisa-kev
  - adobe-commerce-cloud-service
  - saas
category: security
summary: "Adobe released an emergency hotfix on September 7 for CVE-2026-75650, an unauthenticated remote code execution flaw rated 10.0 affecting every Commerce and Magento release from 2.4.4 through 2.4.9. Attacks began September 4. CISA added the flaw to its Known Exploited Vulnerabilities catalog on the 8th, with a September 11 deadline for federal agencies. Adobe deployed firewall rules across its Commerce Cloud fleet before the patch existed."
related:
  - title: "StyleSmuggler: Magento and Adobe Commerce 0-day RCE under active attack"
    url: https://sansec.io/research/stylesmuggler-0day
    date: "September 5, 2026"
  - title: "Urgent Action Required: Critical Security Update Available for Adobe Commerce (APSB26-146)"
    url: https://experienceleague.adobe.com/en/docs/commerce-knowledge-base/kb/announcements/commerce-apsb26-146
    date: "September 7, 2026"
  - title: "Adobe Keeps Patching the Same Cracks: Inside July's Critical Commerce and AEM Bulletins"
    url: https://experiencedigest.org/blog/2026-07-15-apsb26-73-pattern-held/
    date: "July 15, 2026"
---

Adobe published an emergency security bulletin on September 7 for a vulnerability in Adobe Commerce and Magento Open Source that attackers had already been exploiting for three days.

The flaw, **CVE-2026-75650**, is an unauthenticated remote code execution vulnerability rated **10.0** — the maximum score on the CVSS scale. It affects every release from **2.4.4 through 2.4.9**, including Adobe Commerce B2B through 1.5.3. Security firm Sansec, which discovered it and named it **StyleSmuggler**, [reported](https://sansec.io/research/stylesmuggler-0day) that exploitation began on September 4.

The fix ships as hotfix `VULN-39341` under bulletin [APSB26-146](https://experienceleague.adobe.com/en/docs/commerce-knowledge-base/kb/announcements/commerce-apsb26-146), applied as a composer patch. CISA added the vulnerability to its Known Exploited Vulnerabilities catalog on September 8 and set a September 11 remediation deadline for federal civilian agencies.

Merchants should apply the hotfix and then rotate their encryption key and every credential that key protected. Adobe's guidance is explicit on the second step, and it's the one most shops will skip.

One point of confusion worth clearing up: APSB26-146 isn't the same release as [APSB26-138](https://helpx.adobe.com/security/products/magento/apsb26-138.html), Adobe's scheduled September batch, which landed the following day. Two bulletins arrived inside a week, and the out-of-band emergency fix carries the higher number. Both need to be applied.

## How the exploit works

The attack runs in two stages, and both use ordinary Commerce functionality.

In the first stage, the attacker sends a GraphQL request containing manipulated `styles[...]` parameters. Commerce doesn't sanitize them correctly, so PHP code passes validation and is written into internal files — `var/report/` and `var/log/system.log` among them. These are directories most operations teams treat as append-only output rather than as executable content.

In the second stage, the attacker triggers Commerce's built-in **Payment Transaction Failed Reminder** email. The template engine renders the message, and the injected code executes server-side at the moment of rendering. No recipient has to receive the email and no one has to click anything, because delivery isn't part of the attack. The render is.

Neither subsystem is doing anything it wasn't designed to do. The logger writes what it's handed, and the template engine renders what it finds. The vulnerability lives in the seam between them.

Researchers have observed [Rust backdoors and PHP web shells](https://thehackernews.com/2026/09/adobe-patches-magento-zero-day.html) deployed on compromised servers. The attackers are establishing persistence rather than acting immediately.

## A recurring vulnerability class

CVE-2026-75650 is formally classified as improper neutralization of special elements used in a template engine. That class has a history in Commerce.

**CVE-2022-24086**, the mail template injection flaw disclosed in February 2022, was also an unauthenticated RCE in the template layer. It was mass-exploited; the Ondatry group alone compromised more than 4,000 stores. The entry point then was the mail template. The entry point now is the style properties feeding the same renderer.

These aren't the same bug, and the 2022 patch wasn't defective. But they're the same component failing in the same way — a templating layer treating content as instructions rather than as data.

In [July](https://experiencedigest.org/blog/2026-07-15-apsb26-73-pattern-held/), reviewing APSB26-73 and APSB26-74, we argued that Commerce's CVE record reflects a structural weakness at the input-trust boundary rather than a run of bad luck. StyleSmuggler narrows that argument. The recurring component is the template engine, and the recurring failure is that Commerce keeps discovering its renderer is an execution context.

## Timeline

- **September 4** — exploitation begins. No patch exists and no public disclosure has been made.
- **September 5** — Sansec publishes its research. Merchants learn they have been exposed for at least a day, with nothing available to install.
- **September 6–7** — Adobe deploys Fastly VCL rules across its Commerce Cloud environments. Merchants receive notice that the issue remains under review by Adobe's security team.
- **September 7** — Adobe publishes APSB26-146 and the hotfix.
- **September 8** — CISA adds the CVE to the KEV catalog. Adobe's scheduled September bulletin, APSB26-138, ships the same day.
- **September 11** — federal remediation deadline.

## Adobe protected its cloud fleet before it had a fix

The September 6–7 entry is the most consequential item in that sequence. Before Adobe had a patch, it had a firewall rule deployed across infrastructure it operates, applied to customer environments whose owners hadn't requested it.

That response was fast and it was correct. It's also the same measure we recommended in July for the window between disclosure and a validated patch: block the exploit signature at the edge and buy time to test the fix properly.

The difference is who received it. A merchant on Commerce Cloud was covered through the most dangerous 48 hours of the incident by a rule they didn't write, at an edge they don't operate. A merchant running self-hosted Commerce or Magento Open Source behind their own CDN received a research blog post and a weekend. The codebase was identical and the CVE was identical. The defensive posture during the exposure window wasn't, and the CVSS score doesn't capture that difference.

## How it played out on the SaaS product

Adobe Commerce as a Cloud Service — the SaaS product, distinct from the older PaaS offering marketed as Commerce on Cloud — was also affected. Same code lineage, same renderer, same flaw.

According to Adobe's Commerce engineering leadership, remediation on that platform took approximately two hours and required no customer action. Merchants on the Cloud Service didn't apply a patch, write a firewall rule, open a support ticket or schedule a maintenance window.

The claim worth examining isn't that SaaS was immune, because it wasn't. The exposure window was the same. What differed was ownership of the remediation. For self-managed and PaaS merchants, remediation was a four-day coordination exercise; on the Cloud Service, it was a two-hour operation performed by the vendor.

That model carries real costs. A two-hour fix a merchant didn't perform is also a fix they can't verify. There's no patch artifact to inspect, no changelog entry to show an auditor, and no ability to move faster than Adobe if Adobe is slow. The arrangement depends on continued vendor performance, and one incident handled well is a single data point rather than a guarantee.

There's a second architectural difference relevant to this class of vulnerability. On the Cloud Service, extensions run out-of-process through App Builder rather than as in-process PHP in `vendor/`. For flaws that turn on what's permitted to execute inside a store's trust boundary, that's a meaningful distinction. It also means less low-level control, more constraints, and a migration that's substantial work for merchants with deep in-process customization.

## Patching isn't remediation

Merchants exposed between September 4 and whenever they patched should treat compromise as likely until they have evidence otherwise.

Exploitation was active on the 4th and the hotfix arrived on the 7th, leaving a minimum three-day window in which an unauthenticated attacker could place a web shell on any unpatched store. The observed payloads — Rust backdoors and PHP shells — are built to survive remediation. The patch closes the vulnerability. It doesn't remove an attacker who is already resident.

The precedent is CosmicSting in 2024, an XXE flaw that leaked the Commerce encryption key. The leak was the first step in a longer chain, and Sansec ultimately counted 4,275 confirmed store compromises. A meaningful share of those merchants had applied the patch but hadn't rotated the key it protected.

Adobe's guidance for this incident goes further than a typical bulletin. After applying the hotfix, merchants are advised to rotate the encryption key and everything that key secured: admin passwords, REST, SOAP and GraphQL integration tokens, OAuth client secrets, payment gateway credentials, database credentials, SSH and deploy keys, and third-party extension API keys.

That's incident response rather than patch management, and it requires scheduling as such.

## Recommended actions

1. **Apply both bulletins.** `VULN-39341` from APSB26-146 addresses StyleSmuggler. APSB26-138 is the separate scheduled September release. Confirm which has been applied rather than assuming.
2. **Treat the September 11 CISA deadline as the working deadline.** It binds federal civilian agencies only, but it represents the most credible available assessment of how quickly this flaw is being weaponized.
3. **Rotate the encryption key and every credential it protected.** Adobe published the list. Work through it completely.
4. **Search for persistence before declaring the incident closed.** Check `var/report/` and `var/log/system.log` for PHP content, diff `vendor/` and `pub/` against a known-good build, and audit admin users, cron entries, CMS blocks and integration tokens created after September 3.
5. **Verify whether edge protection actually applied.** Commerce Cloud environments received Adobe's Fastly rules. Self-hosted and Open Source deployments didn't. Block `styles[` and its encoded form `styles%5B` on `/graphql` at the edge and leave the rule in place after patching.
6. **Record the operational cost of the response.** Hours, staff, escalation calls and slipped releases are the inputs to the platform decision described below, and they're more accurate captured now than reconstructed later.

## The decision underneath the incident

Most guidance following an incident like this concerns running the patch process better: faster emergency change approval, stronger edge posture, standing extension audits. That advice remains sound, and a number of teams executed it well last week under difficult conditions.

StyleSmuggler is notable because it tested two operating models against the same vulnerability in the same week and produced measurably different outcomes. Self-managed and PaaS merchants spent four days on disclosure, mitigation, patching, credential rotation and compromise assessment. Cloud Service merchants spent two hours, most of them unaware it was happening. The difference wasn't code quality. It was which party held responsibility during the window between disclosure and fix.

For merchants with genuine reasons to hold that responsibility — custom infrastructure, in-process extensions they can't relinquish, compliance requirements that demand an auditable artifact — the four-day model is a defensible trade, provided the runbook matches it. For merchants holding it by default, September's incident is a reasonable prompt to price what that default costs across a year of bulletins.

Adobe's next scheduled Commerce bulletin is expected in October.
