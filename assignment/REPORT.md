# Week 5 assignment — Put a limit on the tunnel

Student ID (last 4 digits only): **4966**

## 1. Analysis: the loop

On s2, I changed the `myTunnel_exact` entry for `dst_id` 3 (handle 2) to send packets
out of port 1, back to s1: `table_modify MyIngress.myTunnel_exact MyIngress.myTunnel_forward 2 1`.
s1 already sends exit 3 to s2, so one packet sent with `--tunnel 3` bounced between them
for ever. In `loop-before.txt` the packet counts went from s1 58 and s2 52 before sending, to
s1 384 and s2 378 just after, and s1 1032 and s2 1025 five seconds later. They kept growing until I exited Mininet.

IPv4's TTL doesn't stop a loop in this program either. `ipv4_forward` decrements the
TTL but never checks it, and `ttl` is a `bit<8>`, so 0 − 1 wraps round to 255 and the
packet keeps going. The tunnel path doesn't touch the TTL at all, which is why tunnelled
packets arrived with TTL 64.

## 2. Design: the hop limit

- **Field:** `bit<8> hop_limit`, at the end of the tunnel header. It is the same size as
  IPv4's TTL, plenty for a 2-switch path, and adds only one byte. Putting it last keeps
  `proto_id` and `dst_id` where old switches expect them.
- **Starting value:** 8 (`send.py --hops`, 0–255). Well above the longest path (2), but
  small enough that a looping packet dies quickly.
- **Where and when:** in ingress. A tunnelled packet that arrives with 0 is dropped;
  otherwise the switch decrements it, then looks up the tunnel table. A packet sent with
  N crosses at most N switches, and the field can never wrap round.
- **Agreement:** the parser and deparser follow the header type, so they needed no
  changes. `send.py` and `receive.py` had to define the same 5-byte header, because
  Step 6 showed what happens when two parts of the path disagree about the layout.

## 3. Implementation

- `tunnel.p4`: added the field. The ingress tunnel branch is now
  `if (hop_limit == 0) drop(); else { decrement; myTunnel_exact.apply(); }`. It is an
  `if/else` because `drop()` only marks the packet, and a later table lookup would
  override it.
- `send.py`: adds the field, with a `--hops` option (default 8) that rejects values
  outside 0–255.
- `receive.py`: the same header; it prints the `hop_limit` that arrived.
- `tunnel_v1.p4`: the unchanged lab program, kept for the mixed rollout.

## 4. Evidence: it works

- **Delivery (`delivery.txt`):** packets sent with `--tunnel 2` and `--tunnel 3` reached
  h2 and h3 with `hop_limit=6` (8, minus one for each switch). A plain ping to h3 still
  worked (TTL 62, 0% loss). A packet sent with `--hops 1` was dropped by s2 and never
  reached h2.
- **The loop ends (`loop-after.txt`):** s1's count went 40 → 45 (+5) and s2's 38 → 42 (+4),
  and stayed there five seconds later. That is 9 visits: forwarded 8 times, then dropped
  by s1 when it arrived with 0. This matches the design.



## 5. Evaluation

### a) Mixed rollout: s1 new, s2 old (`mixed.txt`)

**Prediction (committed before running it):** s2 still reads `dst_id` correctly and
delivers the packet to h2, with `hop_limit` 7, because s2 doesn't decrement it. But s2
parses IPv4 one byte too early. Because it thinks that IPv4 header is valid, its checksum
update overwrites what is really the IPv4 protocol byte, so h2 may get a packet that is
no longer UDP, and `receive.py` may print nothing. In the loop, only s1 decrements, so it
should still end, after about twice as many visits (s1 +9, s2 +8).

**What happened:** every prediction held (`mixed.txt`, run 2). The packet reached h2
with `dst_id` 2 and `hop_limit` `07`: s1 decremented it, and s2 didn't. But the IPv4
protocol byte arrived as `0d` instead of `11` (UDP). s2 parsed IPv4 starting at the
`07`, and its checksum update wrote into what is really the protocol byte. So
`receive.py` printed nothing, although tcpdump shows the packet arrived: the failure is
silent. The loop still ended, with s1 +9 and s2 +8 (48 → 57, 44 → 52): one upgraded
switch on the loop is enough, but it takes twice as many visits.

In run 1, only 48 bytes arrived: the 4-byte tunnel header was missing. My tunnel_v1.p4
still had `packet.emit(hdr.myTunnel)` commented out from Lab Step 6, so s2 never wrote
the header back. I fixed it and reran the experiment. A bug in the "old" program can
hide in a mixed network; only the raw bytes revealed it.

### b) Safe rollout

Putting the new field last isn't enough: as a) shows, an old switch can silently
damage the packet.
1. **New EtherType** (e.g. `0x1213`): the new program parses both types; senders switch to
   the new one only once every switch is upgraded. An old switch drops what it doesn't
   recognise instead of corrupting it.
2. **Two phases:** first deploy a program that reads both formats but still sends the old
   one; once every switch runs it, start sending the new format.

I'd combine both, and upgrade a few switches first as a canary.

### c) Data plane versus control plane

The hop limit catches any loop at run time, whatever caused it, including a table changed
by hand as in C1. `check_paths()` catches loops and missing routes *before* any traffic,
and names the exact path, but only for what is in its input data. The hop limit misses
black holes and only limits the damage, without saying where the loop is. Real networks
use both: checks to get the routes right, and a hop limit as a last line of defence.

### d) Cost at line rate

One extra byte per packet, and 8 more bits to parse and carry through the pipeline. One
comparison and one subtraction, with no new table and no extra memory, so it fits in an
existing stage without slowing it. The main cost is operational: recompiling and reloading
every switch, and the compatibility risk shown in a).


## AI use
I used Claude (Anthropic) to explain P4 and BMv2, to debug my mistakes, to propose the
hop-limit design, to draft the changes to `tunnel.p4`, `send.py` and `receive.py`, and to
draft this report from my results. I ran every experiment myself, checked the results
against the switch logs, and can explain every change. It also helped me find that my first C1 run and my tunnel_v1.p4 used a deparser I had
left commented out from Step 6, so I fixed it and redid both experiments.

## Evidence files

| File | What it shows |
|---|---|
| `evidence/loop-before.txt` | The loop with the lab program: counts growing (58 → 384 → 1032 on s1) |
| `evidence/delivery.txt` | Delivery with `hop_limit` 6, a plain ping, and `--hops 1` dropped |
| `evidence/loop-after.txt` | The same loop with the hop limit: s1 +5, s2 +4, then stops |
| `evidence/mixed.txt` | The mixed rollout: delivery corrupted, loop ends at s1 +9, s2 +8 |
