#!/usr/bin/env python3
"""SNMP OID Test Tool for Meraki Devices.

This tool helps validate and discover SNMP OIDs on Meraki devices.
Use this when adding new SNMP metrics to find the correct OIDs.

Test Devices:
- MS (Switch): 10.0.100.10
- MR (Wireless): 10.0.100.17
- Community: 'knight' (v2c)

Usage:
    # Test a specific OID
    python test_snmp_oids.py get 10.0.100.10 1.3.6.1.2.1.1.1.0
    
    # Walk an OID tree
    python test_snmp_oids.py walk 10.0.100.10 1.3.6.1.2.1.17
    
    # Test common OIDs
    python test_snmp_oids.py common 10.0.100.10
    
    # Search for OIDs by pattern
    python test_snmp_oids.py search 10.0.100.10 1.3.6.1 "topology"
"""

from __future__ import annotations

import argparse
import asyncio
import re
from typing import Any

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    bulk_cmd,
    get_cmd,
)

# Common OIDs to test
COMMON_OIDS = {
    # System MIB
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysObjectID": "1.3.6.1.2.1.1.2.0",
    "sysUpTime": "1.3.6.1.2.1.1.3.0",
    "sysContact": "1.3.6.1.2.1.1.4.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
    "sysLocation": "1.3.6.1.2.1.1.6.0",
    
    # BRIDGE-MIB
    "dot1dBaseBridgeAddress": "1.3.6.1.2.1.17.1.1.0",
    "dot1dBaseNumPorts": "1.3.6.1.2.1.17.1.2.0",
    "dot1dStpProtocolSpecification": "1.3.6.1.2.1.17.2.1.0",
    "dot1dStpTopChanges": "1.3.6.1.2.1.17.2.2.0",
    "dot1dStpDesignatedRoot": "1.3.6.1.2.1.17.2.3.0",
    "dot1dStpRootCost": "1.3.6.1.2.1.17.2.4.0",
    "dot1dStpRootPort": "1.3.6.1.2.1.17.2.5.0",
    
    # IF-MIB
    "ifNumber": "1.3.6.1.2.1.2.1.0",
    "ifTableLastChange": "1.3.6.1.2.1.31.1.5.0",
    
    # Potential Meraki-specific
    "enterprises": "1.3.6.1.4.1",
}

# OID trees to explore
OID_TREES = {
    "system": "1.3.6.1.2.1.1",
    "interfaces": "1.3.6.1.2.1.2",
    "bridge": "1.3.6.1.2.1.17",
    "bridgeStp": "1.3.6.1.2.1.17.2",
    "dot1dTp": "1.3.6.1.2.1.17.4",
    "ifMIB": "1.3.6.1.2.1.31",
    "enterprises": "1.3.6.1.4.1",
    "meraki": "1.3.6.1.4.1.29671",  # Meraki enterprise OID
}


def parse_value(value: Any) -> tuple[str, Any]:
    """Parse SNMP value to Python type.
    
    Returns
    -------
    tuple[str, Any]
        (type_name, parsed_value)

    """
    value_type = value.__class__.__name__
    value_str = value.prettyPrint()
    
    # Handle SNMP error types
    if value_type in {"NoSuchObject", "NoSuchInstance", "EndOfMibView"}:
        return value_type, None
    
    if value_type in {"Integer32", "Integer", "Unsigned32", "Gauge32", "Counter32", "Counter64"}:
        try:
            return value_type, int(value)
        except (ValueError, TypeError):
            return value_type, value_str
    
    elif value_type == "TimeTicks":
        # TimeTicks are in hundredths of a second
        try:
            ticks = int(value)
            seconds = ticks / 100.0
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = seconds % 60
            return value_type, {
                "ticks": ticks,
                "seconds": seconds,
                "formatted": f"{days}d {hours}h {minutes}m {secs:.2f}s"
            }
        except (ValueError, TypeError):
            return value_type, value_str
    
    elif value_type == "OctetString":
        # Check if it's a MAC address (6 bytes)
        if len(value) == 6:
            mac = ":".join(f"{b:02x}" for b in value)
            return value_type, f"{value_str} (MAC: {mac})"
        return value_type, value_str
    
    else:
        return value_type, value_str


async def snmp_get(host: str, oid: str, community: str = "knight", port: int = 161) -> None:
    """Get a specific OID value."""
    print(f"\n=== SNMP GET {oid} from {host} ===")
    
    engine = SnmpEngine()
    
    try:
        transport = await UdpTransportTarget.create((host, port), timeout=5.0, retries=3)
        auth_data = CommunityData(community, mpModel=1)  # v2c
        
        error_indication, error_status, error_index, var_binds = await get_cmd(
            engine,
            auth_data,
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
        
        if error_indication:
            print(f"ERROR: {error_indication}")
            return
        
        if error_status:
            print(f"ERROR: {error_status.prettyPrint()} at {error_index}")
            return
        
        for var_bind in var_binds:
            oid_str = str(var_bind[0])
            value_type, parsed_value = parse_value(var_bind[1])
            
            print(f"OID: {oid_str}")
            print(f"Type: {value_type}")
            print(f"Raw: {var_bind[1].prettyPrint()}")
            print(f"Parsed: {parsed_value}")
            
    except Exception as e:
        print(f"EXCEPTION: {type(e).__name__}: {e}")


async def snmp_walk(host: str, base_oid: str, community: str = "knight", port: int = 161, max_results: int = 100) -> None:
    """Walk an OID tree."""
    print(f"\n=== SNMP WALK {base_oid} from {host} (max {max_results} results) ===")
    
    engine = SnmpEngine()
    results = []
    
    try:
        transport = await UdpTransportTarget.create((host, port), timeout=5.0, retries=3)
        auth_data = CommunityData(community, mpModel=1)  # v2c
        
        # Use bulk operation for efficiency
        error_indication, error_status, error_index, var_binds = await bulk_cmd(
            engine,
            auth_data,
            transport,
            ContextData(),
            0,  # non-repeaters
            25,  # max-repetitions
            ObjectType(ObjectIdentity(base_oid)),
        )
        
        if error_indication:
            print(f"ERROR: {error_indication}")
            return
        
        if error_status:
            print(f"ERROR: {error_status.prettyPrint()} at {error_index}")
            return
        
        count = 0
        for var_bind in var_binds:
            oid_str = str(var_bind[0])
            
            # Stop if we've walked outside the base OID
            if not oid_str.startswith(base_oid):
                break
                
            value_type, parsed_value = parse_value(var_bind[1])
            
            # Skip NoSuchObject entries
            if value_type in {"NoSuchObject", "NoSuchInstance", "EndOfMibView"}:
                continue
            
            results.append({
                "oid": oid_str,
                "type": value_type,
                "raw": var_bind[1].prettyPrint(),
                "parsed": parsed_value,
            })
            
            count += 1
            if count >= max_results:
                print(f"\n(Stopped at {max_results} results)")
                break
        
        # Display results
        for result in results:
            print(f"\nOID: {result['oid']}")
            print(f"  Type: {result['type']}")
            print(f"  Value: {result['parsed']}")
            
        print(f"\nTotal: {len(results)} OIDs found")
        
    except Exception as e:
        print(f"EXCEPTION: {type(e).__name__}: {e}")


async def test_common_oids(host: str, community: str = "knight") -> None:
    """Test common OIDs to see what's available."""
    print(f"\n=== Testing Common OIDs on {host} ===")
    
    available = []
    unavailable = []
    
    for name, oid in COMMON_OIDS.items():
        engine = SnmpEngine()
        
        try:
            transport = await UdpTransportTarget.create((host, 161), timeout=2.0, retries=1)
            auth_data = CommunityData(community, mpModel=1)
            
            error_indication, error_status, error_index, var_binds = await get_cmd(
                engine,
                auth_data,
                transport,
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
            
            if error_indication or error_status:
                unavailable.append(name)
            else:
                for var_bind in var_binds:
                    value_type, parsed_value = parse_value(var_bind[1])
                    if value_type not in {"NoSuchObject", "NoSuchInstance"}:
                        available.append((name, oid, parsed_value))
                    else:
                        unavailable.append(name)
                        
        except Exception:
            unavailable.append(name)
    
    print("\n✓ Available OIDs:")
    for name, oid, value in available:
        print(f"  {name:<30} {oid:<30} = {value}")
    
    print(f"\n✗ Unavailable OIDs ({len(unavailable)}):")
    for name in unavailable:
        print(f"  {name}")


async def search_oids(host: str, base_oid: str, pattern: str, community: str = "knight") -> None:
    """Search for OIDs containing a pattern in their values."""
    print(f"\n=== Searching for '{pattern}' under {base_oid} on {host} ===")
    
    engine = SnmpEngine()
    matches = []
    
    try:
        transport = await UdpTransportTarget.create((host, 161), timeout=5.0, retries=3)
        auth_data = CommunityData(community, mpModel=1)
        
        error_indication, error_status, error_index, var_binds = await bulk_cmd(
            engine,
            auth_data,
            transport,
            ContextData(),
            0,
            50,
            ObjectType(ObjectIdentity(base_oid)),
        )
        
        if error_indication or error_status:
            print(f"ERROR: {error_indication or error_status}")
            return
        
        regex = re.compile(pattern, re.IGNORECASE)
        
        for var_bind in var_binds:
            oid_str = str(var_bind[0])
            
            if not oid_str.startswith(base_oid):
                break
            
            value_str = var_bind[1].prettyPrint()
            value_type = var_bind[1].__class__.__name__
            
            if value_type in {"NoSuchObject", "NoSuchInstance", "EndOfMibView"}:
                continue
            
            # Search in both OID and value
            if regex.search(oid_str) or regex.search(value_str):
                matches.append((oid_str, value_type, value_str))
        
        if matches:
            print(f"\nFound {len(matches)} matches:")
            for oid, vtype, value in matches:
                print(f"\n  OID: {oid}")
                print(f"  Type: {vtype}")
                print(f"  Value: {value}")
        else:
            print("\nNo matches found")
            
    except Exception as e:
        print(f"EXCEPTION: {type(e).__name__}: {e}")


async def explore_trees(host: str, community: str = "knight") -> None:
    """Explore common OID trees to see what's available."""
    print(f"\n=== Exploring OID Trees on {host} ===")
    
    for tree_name, tree_oid in OID_TREES.items():
        print(f"\n--- {tree_name} ({tree_oid}) ---")
        
        engine = SnmpEngine()
        count = 0
        
        try:
            transport = await UdpTransportTarget.create((host, 161), timeout=2.0, retries=1)
            auth_data = CommunityData(community, mpModel=1)
            
            error_indication, error_status, error_index, var_binds = await bulk_cmd(
                engine,
                auth_data,
                transport,
                ContextData(),
                0,
                10,  # Just get a sample
                ObjectType(ObjectIdentity(tree_oid)),
            )
            
            if error_indication or error_status:
                print("  ERROR: Not accessible")
                continue
            
            for var_bind in var_binds:
                oid_str = str(var_bind[0])
                
                if not oid_str.startswith(tree_oid):
                    break
                
                value_type = var_bind[1].__class__.__name__
                
                if value_type not in {"NoSuchObject", "NoSuchInstance", "EndOfMibView"}:
                    count += 1
                    if count <= 3:  # Show first 3 as examples
                        print(f"  Example: {oid_str} ({value_type})")
            
            if count > 0:
                print(f"  ✓ Available ({count}+ OIDs)")
            else:
                print("  ✗ No data")
                
        except Exception:
            print("  ERROR: Connection failed")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="SNMP OID Test Tool for Meraki Devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test sysDescr on MS switch
  %(prog)s get 10.0.100.10 1.3.6.1.2.1.1.1.0
  
  # Walk bridge MIB on MS switch
  %(prog)s walk 10.0.100.10 1.3.6.1.2.1.17
  
  # Test common OIDs on MR access point
  %(prog)s common 10.0.100.17
  
  # Search for 'topology' in enterprise MIBs
  %(prog)s search 10.0.100.10 1.3.6.1.4.1 topology
  
  # Explore available OID trees
  %(prog)s explore 10.0.100.10
  
Default test devices:
  MS (Switch):   10.0.100.10
  MR (Wireless): 10.0.100.17
  Community:     knight (v2c)
        """
    )
    
    parser.add_argument("command", choices=["get", "walk", "common", "search", "explore"],
                        help="Command to run")
    parser.add_argument("host", help="Device IP address")
    parser.add_argument("oid", nargs="?", help="OID (for get/walk commands)")
    parser.add_argument("pattern", nargs="?", help="Search pattern (for search command)")
    parser.add_argument("-c", "--community", default="knight", help="SNMP community (default: knight)")
    parser.add_argument("-p", "--port", type=int, default=161, help="SNMP port (default: 161)")
    parser.add_argument("-m", "--max", type=int, default=100, help="Max results for walk (default: 100)")
    
    args = parser.parse_args()
    
    if args.command in ["get", "walk"] and not args.oid:
        parser.error(f"{args.command} command requires an OID")
    
    if args.command == "search" and not args.pattern:
        parser.error("search command requires a pattern")
    
    # Run the appropriate command
    if args.command == "get":
        asyncio.run(snmp_get(args.host, args.oid, args.community, args.port))
    elif args.command == "walk":
        asyncio.run(snmp_walk(args.host, args.oid, args.community, args.port, args.max))
    elif args.command == "common":
        asyncio.run(test_common_oids(args.host, args.community))
    elif args.command == "search":
        base_oid = args.oid if args.oid else "1.3.6.1"
        asyncio.run(search_oids(args.host, base_oid, args.pattern, args.community))
    elif args.command == "explore":
        asyncio.run(explore_trees(args.host, args.community))


if __name__ == "__main__":
    main()
