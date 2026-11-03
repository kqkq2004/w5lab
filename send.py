#!/usr/bin/env python3
"""Send one UDP packet, optionally inside the custom tunnel header.

    python3 send.py <ip address> "<message>"                       plain IPv4
    python3 send.py <ip address> "<message>" --tunnel N            tunnelled to exit N
    python3 send.py <ip address> "<message>" --tunnel N --hops H   ...with a hop limit of H
"""
import argparse

from scapy.all import IP, UDP, ByteField, Ether, Packet, ShortField, bind_layers, get_if_hwaddr, get_if_list, sendp


class MyTunnel(Packet):
    name = "MyTunnel"
    # Must match myTunnel_t in tunnel.p4, field for field: bit<16>, bit<16>, bit<8>.
    fields_desc = [
        ShortField("proto_id", 0x0800),
        ShortField("dst_id", 0),
        ByteField("hop_limit", 8),  # how many more switches the packet may cross
    ]


bind_layers(Ether, MyTunnel, type=0x1212)
bind_layers(MyTunnel, IP, proto_id=0x0800)


def hop_count(text):
    """--hops must fit the 8-bit hop_limit field."""
    value = int(text)
    if not 0 <= value <= 255:
        raise argparse.ArgumentTypeError("--hops must be between 0 and 255")
    return value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ip")
    ap.add_argument("message")
    ap.add_argument("--tunnel", type=int, metavar="N", help="tunnel exit to deliver to")
    ap.add_argument("--hops", type=hop_count, default=8, metavar="H",
                    help="starting hop limit for a tunnelled packet (default 8)")
    args = ap.parse_args()

    iface = next(i for i in get_if_list() if i.endswith("-eth0"))
    pkt = Ether(src=get_if_hwaddr(iface), dst="ff:ff:ff:ff:ff:ff")
    if args.tunnel is not None:
        pkt = pkt / MyTunnel(dst_id=args.tunnel, hop_limit=args.hops)
    pkt = pkt / IP(dst=args.ip) / UDP(sport=4321, dport=4321) / args.message
    pkt.show2()
    sendp(pkt, iface=iface, verbose=False)
    print(f"Sent from {iface}.")


if __name__ == "__main__":
    main()