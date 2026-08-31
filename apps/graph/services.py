"""
Graph-based relationship analysis for fraud investigations.

The graph connects:
    customer <-> device
    customer <-> IP address
    customer <-> transaction

The analysis can be run for:
    - a customer/device/IP combination
    - a specific transaction
    - optionally, a historical timestamp cutoff

The function returns bounded, JSON-serializable dictionaries.
"""

from collections import defaultdict

import networkx as nx

from apps.transactions.models import Transaction


def analyze_relationships(
    customer_id,
    device_id,
    ip_id,
    transaction_id=None,
    timestamp_cutoff=None,
):
    """
    Analyze relationships between a customer, devices, IP addresses,
    and transactions.

    Parameters
    ----------
    customer_id : str
        Customer identifier.

    device_id : str
        Device identifier associated with the transaction.

    ip_id : str
        IP identifier associated with the transaction.

    transaction_id : str, optional
        Current transaction identifier. When supplied, the current
        transaction is excluded from the list of "other transactions".

    timestamp_cutoff : datetime, optional
        If supplied, only transactions at or before this timestamp
        are included.

    Returns
    -------
    dict
        JSON-serializable relationship analysis.
    """

    # ------------------------------------------------------------------
    # Build the transaction queryset
    # ------------------------------------------------------------------

    queryset = (
        Transaction.objects
        .select_related(
            "customer",
            "device",
            "ip_address",
        )
        .all()
    )

    if timestamp_cutoff is not None:
        queryset = queryset.filter(timestamp__lte=timestamp_cutoff)

    # ------------------------------------------------------------------
    # Build graph
    # ------------------------------------------------------------------

    G = nx.Graph()

    # Track transactions represented in the graph.
    rows = []

    for txn in queryset.iterator():
        txn_customer_id = txn.customer.customer_id
        txn_device_id = txn.device.device_id
        txn_ip_id = txn.ip_address.ip_id
        txn_transaction_id = txn.transaction_id

        rows.append(
            (
                txn_customer_id,
                txn_device_id,
                txn_ip_id,
                txn_transaction_id,
            )
        )

        customer_node = ("customer", txn_customer_id)
        device_node = ("device", txn_device_id)
        ip_node = ("ip", txn_ip_id)
        transaction_node = ("transaction", txn_transaction_id)

        G.add_node(customer_node)
        G.add_node(device_node)
        G.add_node(ip_node)
        G.add_node(transaction_node)

        # Customer <-> Device
        G.add_edge(
            customer_node,
            device_node,
            relationship="shared_device",
        )

        # Customer <-> IP
        G.add_edge(
            customer_node,
            ip_node,
            relationship="shared_ip",
        )

        # Customer <-> Transaction
        G.add_edge(
            customer_node,
            transaction_node,
            relationship="owns_transaction",
        )

    # ------------------------------------------------------------------
    # Ensure the requested entities exist in the graph even if there
    # are no matching transaction rows.
    # ------------------------------------------------------------------

    seed_node = ("customer", customer_id)

    G.add_node(seed_node)
    G.add_node(("device", device_id))
    G.add_node(("ip", ip_id))

    G.add_edge(
        seed_node,
        ("device", device_id),
        relationship="shared_device",
    )

    G.add_edge(
        seed_node,
        ("ip", ip_id),
        relationship="shared_ip",
    )

    # If the caller gave us the current transaction, add it explicitly.
    if transaction_id:
        transaction_node = ("transaction", transaction_id)

        G.add_node(transaction_node)

        G.add_edge(
            seed_node,
            transaction_node,
            relationship="owns_transaction",
        )

    # ------------------------------------------------------------------
    # Find connected component around the customer.
    # ------------------------------------------------------------------

    try:
        component = nx.node_connected_component(G, seed_node)
    except nx.NetworkXError:
        component = {seed_node}

    # ------------------------------------------------------------------
    # Find customers connected through shared devices or IP addresses.
    # ------------------------------------------------------------------

    connected_customers = []

    for node in component:
        if not isinstance(node, tuple) or len(node) != 2:
            continue

        node_type, node_id = node

        if node_type != "customer":
            continue

        if node_id == customer_id:
            continue

        connected_customers.append(node_id)

    connected_customers = sorted(set(connected_customers))

    # ------------------------------------------------------------------
    # Find devices in the customer's connected component.
    # ------------------------------------------------------------------

    connected_devices = sorted(
        {
            node[1]
            for node in component
            if isinstance(node, tuple)
            and len(node) == 2
            and node[0] == "device"
        }
    )

    # ------------------------------------------------------------------
    # Find IP addresses in the customer's connected component.
    # ------------------------------------------------------------------

    connected_ips = sorted(
        {
            node[1]
            for node in component
            if isinstance(node, tuple)
            and len(node) == 2
            and node[0] == "ip"
        }
    )

    # ------------------------------------------------------------------
    # Find transactions in the connected component.
    # ------------------------------------------------------------------

    connected_transactions = sorted(
        {
            node[1]
            for node in component
            if isinstance(node, tuple)
            and len(node) == 2
            and node[0] == "transaction"
            and node[1] != transaction_id
        }
    )

    # ------------------------------------------------------------------
    # Determine direct sharing.
    # ------------------------------------------------------------------

    shared_device_customers = sorted(
        {
            customer
            for customer, device, ip, txn in rows
            if device == device_id
            and customer != customer_id
        }
    )

    shared_ip_customers = sorted(
        {
            customer
            for customer, device, ip, txn in rows
            if ip == ip_id
            and customer != customer_id
        }
    )

    # ------------------------------------------------------------------
    # Build relationship details.
    # ------------------------------------------------------------------

    relationships = []

    for other_customer in connected_customers:
        shares_device = other_customer in shared_device_customers
        shares_ip = other_customer in shared_ip_customers

        relationship_types = []

        if shares_device:
            relationship_types.append("shared_device")

        if shares_ip:
            relationship_types.append("shared_ip")

        relationships.append(
            {
                "customer_id": other_customer,
                "relationship_types": relationship_types,
                "shares_device": shares_device,
                "shares_ip": shares_ip,
            }
        )

    # ------------------------------------------------------------------
    # Calculate simple graph statistics.
    # ------------------------------------------------------------------

    component_customer_count = sum(
        1
        for node in component
        if isinstance(node, tuple)
        and len(node) == 2
        and node[0] == "customer"
    )

    component_device_count = sum(
        1
        for node in component
        if isinstance(node, tuple)
        and len(node) == 2
        and node[0] == "device"
    )

    component_ip_count = sum(
        1
        for node in component
        if isinstance(node, tuple)
        and len(node) == 2
        and node[0] == "ip"
    )

    component_transaction_count = sum(
        1
        for node in component
        if isinstance(node, tuple)
        and len(node) == 2
        and node[0] == "transaction"
    )

    # ------------------------------------------------------------------
    # Fraud-ring indication.
    #
    # A customer connected to other customers through the same device
    # or IP is potentially part of a shared-identifier network.
    # ------------------------------------------------------------------

    potential_fraud_ring = bool(connected_customers)

    # ------------------------------------------------------------------
    # Return bounded JSON-serializable result.
    # ------------------------------------------------------------------

    return {
        "customer_id": customer_id,
        "device_id": device_id,
        "ip_id": ip_id,
        "transaction_id": transaction_id,
        "timestamp_cutoff": (
            timestamp_cutoff.isoformat()
            if timestamp_cutoff is not None
            else None
        ),
        "connected_customers": connected_customers,
        "connected_devices": connected_devices,
        "connected_ips": connected_ips,
        "connected_transactions": connected_transactions,
        "shared_device_customers": shared_device_customers,
        "shared_ip_customers": shared_ip_customers,
        "relationships": relationships,
        "potential_fraud_ring": potential_fraud_ring,
        "graph_statistics": {
            "customers": component_customer_count,
            "devices": component_device_count,
            "ips": component_ip_count,
            "transactions": component_transaction_count,
        },
    }


def get_customer_graph(customer_id, timestamp_cutoff=None):
    """
    Convenience function for obtaining the graph relationships for a
    customer without requiring a specific transaction.

    The customer's most recent transaction is used to determine the
    relevant device and IP identifiers.
    """

    queryset = (
        Transaction.objects
        .select_related(
            "customer",
            "device",
            "ip_address",
        )
        .filter(customer__customer_id=customer_id)
        .order_by("-timestamp")
    )

    if timestamp_cutoff is not None:
        queryset = queryset.filter(timestamp__lte=timestamp_cutoff)

    txn = queryset.first()

    if txn is None:
        return {
            "error": f"No transaction found for customer {customer_id}"
        }

    return analyze_relationships(
        customer_id=txn.customer.customer_id,
        device_id=txn.device.device_id,
        ip_id=txn.ip_address.ip_id,
        transaction_id=txn.transaction_id,
        timestamp_cutoff=timestamp_cutoff,
    )