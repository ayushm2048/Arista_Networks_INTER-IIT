import xml.etree.ElementTree as ET
import sys
import os
import copy

# =========================
# Top-level Helpers (New)
# =========================
#def _build_eth_interface(device_elem, iface_id, iface_name, connected_to_str, ip=None, mask=None, mac_address=None):
def _build_eth_interface(iface_id, iface_name, connected_to_str, ip=None, mask=None, mac_address=None):

    """Build a fresh Ethernet interface (no templates) with sensible defaults."""
    iface = ET.Element("INTERFACE", {
        "ID": str(iface_id),
        "INTERFACE_NAME": iface_name,
        "INTERFACE_TYPE": "ETHERNET"
    })

    # NETWORK_LAYER (IPv4 + ARP)
    layer_net = ET.SubElement(iface, "LAYER", {"TYPE": "NETWORK_LAYER"})
    net_ipv4 = ET.SubElement(layer_net, "NETWORK_PROTOCOL", {"NAME": "IPV4", "SETPROPERTY": "TRUE"})
    ET.SubElement(net_ipv4, "PROTOCOL_PROPERTY", {
        "IP_ADDRESS": ip or "",
        "SUBNET_MASK": mask or "",
        "DEFAULT_GATEWAY": ""
    })
    arp = ET.SubElement(layer_net, "PROTOCOL", {"NAME": "ARP", "SETPROPERTY": "TRUE"})
    ET.SubElement(arp, "PROTOCOL_PROPERTY", {"ARP_RETRY_INTERVAL": "10", "ARP_RETRY_LIMIT": "3"})

    # DATALINK_LAYER (ETHERNET)
    layer_dl = ET.SubElement(iface, "LAYER", {"TYPE": "DATALINK_LAYER"})
    eth_dl = ET.SubElement(layer_dl, "PROTOCOL", {"NAME": "ETHERNET", "SETPROPERTY": "TRUE"})
    ET.SubElement(eth_dl, "PROTOCOL_PROPERTY", {"MAC_ADDRESS": mac_address or ""})

    # PHYSICAL_LAYER (ETHERNET, wired)
    layer_phy = ET.SubElement(iface, "LAYER", {"TYPE": "PHYSICAL_LAYER"})
    eth_phy = ET.SubElement(layer_phy, "PROTOCOL", {"NAME": "ETHERNET", "SETPROPERTY": "TRUE"})
    ET.SubElement(eth_phy, "PROTOCOL_PROPERTY", {
        "CONNECTION_MEDIUM": "WIRED",
        "CONNECTED_TO": connected_to_str
        # "LINK_TYPE": "WIRED"  # uncomment if your config requires it
    })
    return iface


def _ensure_device_ethernet_interface_no_template(config_manager, device_obj, connected_to_str, ip=None, mask=None):
    """
    Ensure an ETHERNET interface exists. If present, update it; else build from scratch.
    Returns interface ID (string).
    """
    dev_elem = device_obj.element
    # Reuse existing
    for iface in dev_elem.findall('INTERFACE'):
        if iface.get('INTERFACE_TYPE') == 'ETHERNET':
            iface_id = iface.get('ID')
            # CONNECTED_TO
            phy_props = iface.find('.//LAYER[@TYPE="PHYSICAL_LAYER"]//PROTOCOL[@NAME="ETHERNET"]/PROTOCOL_PROPERTY')
            if phy_props is not None and connected_to_str:
                phy_props.set("CONNECTED_TO", connected_to_str)
            # IPv4
            net_ipv4 = iface.find('.//LAYER[@TYPE="NETWORK_LAYER"]//NETWORK_PROTOCOL[@NAME="IPV4"]/PROTOCOL_PROPERTY')
            if net_ipv4 is not None and ip and mask:
                net_ipv4.set("IP_ADDRESS", ip)
                net_ipv4.set("SUBNET_MASK", mask)
            return iface_id

    # Create fresh
    new_iface_id = config_manager._get_next_interface_id(dev_elem)
    mac = config_manager._generate_mac(dev_elem.get("DEVICE_ID"), new_iface_id)
    iface_name = f"Interface_{new_iface_id} (Ethernet)"

    new_iface = _build_eth_interface(
    iface_id=new_iface_id,
    iface_name=f"Interface_{new_iface_id} (Ethernet)",
    connected_to_str=connected_to_str,
    ip=ip, mask=mask, mac_address=mac
    )

    dev_elem.append(new_iface)
    return str(new_iface_id)


def _build_wired_link_element(link_id, dev_a, a_iface_id, dev_b, b_iface_id,
                              link_name=None,
                              link_speed_up="100", link_speed_down="100",
                              err_up="1E-07", err_down="1E-07",
                              prop_delay_up="5", prop_delay_down="5",
                              key="P2PWired",
                              link_type="POINT_TO_POINT",
                              link_mode="FULL_DUPLEX"):
    """Create a WIRED <LINK> from scratch (no template)."""
    link_name = link_name or str(link_id)
    link = ET.Element("LINK", {
        "LINK_ID": str(link_id),
        "LINK_NAME": link_name,
        "DEVICE_COUNT": "2",
        "KEY": key,
        "TYPE": link_type,
        "MEDIUM": "WIRED",
        "LINK_MODE": link_mode,
        "LINK_SPEED_UP": link_speed_up,
        "LINK_SPEED_DOWN": link_speed_down
    })

    ET.SubElement(link, "MEDIUM_PROPERTY", {
        "SUBLAYER_NAME": "Medium Property",
        "ERROR_RATE_UP": err_up,
        "ERROR_RATE_DOWN": err_down,
        "PROPAGATION_DELAY_UP": prop_delay_up,
        "PROPAGATION_DELAY_DOWN": prop_delay_down
    })

    ET.SubElement(link, "DEVICE", {
        "DEVICE_ID": dev_a.element.get("DEVICE_ID"),
        "INTERFACE_ID": str(a_iface_id),
        "NAME": dev_a.name
    })
    ET.SubElement(link, "DEVICE", {
        "DEVICE_ID": dev_b.element.get("DEVICE_ID"),
        "INTERFACE_ID": str(b_iface_id),
        "NAME": dev_b.name
    })

    ET.SubElement(link, "GRAPHICS", {"Name": link_name, "Color": "#4d4d4d", "Width": "1"})
    return link


def _pick_from_list(prompt, items, label=lambda x: x, allow_multi=False):
    """Generic picker for CLI lists (supports multi-select)."""
    print(prompt)
    for i, it in enumerate(items, 1):
        print(f"  {i}. {label(it)}")
    if allow_multi:
        raw = input("Enter numbers (e.g., 1,3,4): ").strip()
        try:
            idxs = [int(x) - 1 for x in raw.split(",") if x.strip()]
            sel = [items[i] for i in idxs if 0 <= i < len(items)]
            if not sel:
                print("No valid selections.")
            return sel
        except ValueError:
            print("Invalid input.")
            return []
    else:
        try:
            idx = int(input("Enter number: ")) - 1
            if 0 <= idx < len(items):
                return items[idx]
            print("Invalid selection.")
            return None
        except ValueError:
            print("Invalid input.")
            return None


class NetSimConfig:
    """
    Manages loading, parsing, and saving the NetSim Config.netsim XML file.
    """
    def __init__(self, config_file):
        self.config_file = config_file
        self.tree = None
        self.root = None
        self.device_config_element = None
        self.connection_element = None
        self.load_config()

    def load_config(self):
        try:
            self.tree = ET.parse(self.config_file)
            self.root = self.tree.getroot()
            self.device_config_element = self.root.find('.//DEVICE_CONFIGURATION')
            if self.device_config_element is None:
                print("Error: <DEVICE_CONFIGURATION> tag not found.")
                sys.exit(1)
            self.connection_element = self.root.find('.//CONNECTION')
            if self.connection_element is None:
                print("Error: <CONNECTION> tag not found.")
                sys.exit(1)
            print(f"Successfully loaded '{self.config_file}'")
        except ET.ParseError as e:
            print(f"Error parsing XML file: {e}")
            sys.exit(1)
        except FileNotFoundError:
            print(f"Error: Configuration file '{self.config_file}' not found.")
            sys.exit(1)

    # -------- Finders ----------
    def get_device_by_name(self, name):
        if self.device_config_element is not None:
            for device in self.device_config_element.findall('DEVICE'):
                if device.get('DEVICE_NAME') == name:
                    return device
        return None

    def get_all_access_points(self):
        access_points = []
        if self.device_config_element is not None:
            for device in self.device_config_element.findall('DEVICE'):
                if device.get('TYPE') == 'ACCESSPOINT':
                    access_points.append(AccessPoint(device))
        return access_points

    def get_all_routers(self):
        routers = []
        if self.device_config_element is not None:
            for device in self.device_config_element.findall('DEVICE'):
                if device.get('TYPE') == 'ROUTER':
                    routers.append(Router(device))
        return routers

    def get_all_wireless_nodes(self):
        nodes = []
        if self.device_config_element is not None:
            for device in self.device_config_element.findall('DEVICE'):
                if device.get('TYPE') == 'NODE':
                    nodes.append(WirelessNode(device))
        return nodes

    def get_all_links(self):
        links = []
        if self.connection_element is not None:
            for link_elem in self.connection_element.findall('LINK'):
                links.append(Link(link_elem))
        return links

    def get_all_devices_wrapped(self):
        """
        Return ALL devices as wrapped objects (AP/Router/WirelessNode).
        Works regardless of how many of each exist.
        """
        result = []
        if self.device_config_element is None:
            return result
        for dev in self.device_config_element.findall('DEVICE'):
            t = dev.get('TYPE')
            if t == 'ACCESSPOINT':
                result.append(AccessPoint(dev))
            elif t == 'ROUTER':
                result.append(Router(dev))
            else:  # TYPE == 'NODE'
                result.append(WirelessNode(dev))
        return result

    # -------- Save ----------
    def save_config(self, output_file):
        try:
            self.tree.write(output_file, encoding='UTF-8', xml_declaration=True)
            print(f"Configuration successfully saved to '{output_file}'")
        except Exception as e:
            print(f"Error saving file: {e}")

    # -------- ID helpers ----------
    def _get_next_device_id(self):
        max_id = 0
        if self.device_config_element is not None:
            for device in self.device_config_element.findall('DEVICE'):
                try:
                    dev_id = int(device.get('DEVICE_ID', 0))
                    if dev_id > max_id:
                        max_id = dev_id
                except ValueError:
                    continue
        return max_id + 1

    def _get_next_link_id(self):
        max_id = 0
        if self.connection_element is not None:
            for link in self.connection_element.findall('LINK'):
                try:
                    link_id = int(link.get('LINK_ID', 0))
                    if link_id > max_id:
                        max_id = link_id
                except ValueError:
                    continue
        return max_id + 1

    def _get_next_interface_id(self, device_element):
        max_id = 0
        for iface in device_element.findall('INTERFACE'):
            try:
                iface_id = int(iface.get('ID', 0))
                if iface_id > max_id:
                    max_id = iface_id
            except ValueError:
                continue
        device_element.set('INTERFACE_COUNT', str(max_id + 1))
        return max_id + 1

    # -------- Template utilities (existing) ----------
    def _get_template_device(self, device_type):
        if self.device_config_element is not None:
            for device in self.device_config_element.findall('DEVICE'):
                if device.get('TYPE') == device_type:
                    return device
        return None

    def _get_template_interface(self, device_type, interface_type):
        template_device = self._get_template_device(device_type)
        if template_device is not None:
            for iface in template_device.findall('INTERFACE'):
                if iface.get('INTERFACE_TYPE') == interface_type:
                    return copy.deepcopy(iface)
        print(f"Error: Could not find template interface for {device_type}/{interface_type}")
        return None

    def _get_template_link(self, medium_type):
        if self.connection_element is not None:
            for link in self.connection_element.findall('LINK'):
                if link.get('MEDIUM') == medium_type:
                    return copy.deepcopy(link)
        print(f"Error: Could not find template link for MEDIUM={medium_type}")
        return None

    def _generate_mac(self, device_id, interface_id):
        try:
            dev_id_str = str(device_id).zfill(5)
            iface_id_str = str(interface_id).zfill(3)
            return f"155D{dev_id_str}{iface_id_str}"
        except Exception:
            return "155D00000000"

    def _update_device_count(self):
        if self.device_config_element is not None:
            count = len(self.device_config_element.findall('DEVICE'))
            self.device_config_element.set('DEVICE_COUNT', str(count))

    # -------- Create devices (existing) ----------
    def create_access_point(self, x, y):
        if self.device_config_element is None:
            print("Error: DEVICE_CONFIGURATION not found.")
            return None
        next_id = self._get_next_device_id()
        name = f"Access_Point_{next_id}"
        device_attrs = {
            "KEY": "Accesspoint",
            "DEVICE_NAME": name,
            "DEVICE_ID": str(next_id),
            "TYPE": "ACCESSPOINT",
            "WIRESHARK_OPTION": "Disable",
            "INTERFACE_COUNT": "0",
            "DEVICE_ICON": "AccessPoint.png"
        }
        new_ap = ET.Element("DEVICE", device_attrs)
        pos_attrs = {
            "X_OR_LON": str(x), "Y_OR_LAT": str(y), "Z": "0.00",
            "COORDINATE_SYSTEM": "Cartesian", "ICON_ROTATION": "0"
        }
        ET.SubElement(new_ap, "POS_3D", pos_attrs)
        self.device_config_element.append(new_ap)
        self._update_device_count()
        print(f"Successfully created AccessPoint '{name}' with ID {next_id}.")
        return AccessPoint(new_ap)

    def create_router(self, x, y):
        if self.device_config_element is None:
            print("Error: DEVICE_CONFIGURATION not found.")
            return None
        template_router = self._get_template_device("ROUTER")
        if template_router is None:
            print("Error: Could not find a template Router to copy layers from.")
            return None
        next_id = self._get_next_device_id()
        name = f"Router_{next_id}"
        device_attrs = {
            "KEY": "Router",
            "DEVICE_NAME": name,
            "DEVICE_ID": str(next_id),
            "TYPE": "ROUTER",
            "WIRESHARK_OPTION": "Disable",
            "INTERFACE_COUNT": "0",
            "DEVICE_ICON": "InternalRouter.png"
        }
        new_router = ET.Element("DEVICE", device_attrs)
        pos_attrs = {
            "X_OR_LON": str(x), "Y_OR_LAT": str(y), "Z": "0.00",
            "COORDINATE_SYSTEM": "Cartesian", "ICON_ROTATION": "0"
        }
        ET.SubElement(new_router, "POS_3D", pos_attrs)
        layers_to_clone = template_router.findall('LAYER')
        for layer in layers_to_clone:
            cloned_layer = copy.deepcopy(layer)
            ospf_prop = cloned_layer.find('.//ROUTING_PROTOCOL[@NAME="OSPF"]/PROTOCOL_PROPERTY')
            if ospf_prop is not None:
                for iface in ospf_prop.findall('INTERFACE'):
                    ospf_prop.remove(iface)
            new_router.append(cloned_layer)
        self.device_config_element.append(new_router)
        self._update_device_count()
        print(f"Successfully created Router '{name}' with ID {next_id}.")
        return Router(new_router)

    def create_wireless_node(self, x, y):
        if self.device_config_element is None:
            print("Error: DEVICE_CONFIGURATION not found.")
            return None
        template_node = self._get_template_device("NODE")
        if template_node is None:
            print("Error: Could not find a template Wireless Node to copy layers from.")
            return None
        next_id = self._get_next_device_id()
        name = f"Wireless_Node_{next_id}"
        device_attrs = {
            "KEY": "WirelessNode",
            "DEVICE_NAME": name,
            "DEVICE_ID": str(next_id),
            "TYPE": "NODE",
            "WIRESHARK_OPTION": "Disable",
            "INTERFACE_COUNT": "0",
            "DEVICE_ICON": "WirelessNode.png"
        }
        new_node = ET.Element("DEVICE", device_attrs)
        pos_attrs = {
            "X_OR_LON": str(x), "Y_OR_LAT": str(y), "Z": "0.00",
            "COORDINATE_SYSTEM": "Cartesian", "ICON_ROTATION": "0"
        }
        ET.SubElement(new_node, "POS_3D", pos_attrs)
        layers_to_clone = template_node.findall('LAYER')
        for layer in layers_to_clone:
            cloned_layer = copy.deepcopy(layer)
            new_node.append(cloned_layer)
        self.device_config_element.append(new_node)
        self._update_device_count()
        print(f"Successfully created Wireless Node '{name}' with ID {next_id}.")
        return WirelessNode(new_node)

    # -------- Create links (existing wireless + new wired) ----------
    def create_wireless_link(self, access_point, wireless_nodes):
        if not wireless_nodes:
            print("Error: No wireless nodes selected for the link.")
            return
        print(f"\nCreating new wireless link for {access_point.name}...")
        new_link_id = self._get_next_link_id()
        subnet_base = f"192.{167 + new_link_id}.0"
        gateway_ip = f"{subnet_base}.1"
        subnet_mask = "255.255.0.0"
        print(f"  New Link ID: {new_link_id}")
        print(f"  New Subnet: {subnet_base}.0/16")
        all_devices_on_link = [access_point] + wireless_nodes
        connected_to_str = " ... ".join([d.name for d in all_devices_on_link])
        ap_iface_id = access_point.ensure_wireless_interface(self, connected_to_str)
        node_interface_ids = {}
        for i, node in enumerate(wireless_nodes):
            host_id = i + 2
            node_ip = f"{subnet_base}.{host_id}"
            node_iface_id = node.ensure_wireless_interface(self, connected_to_str, node_ip, subnet_mask, gateway_ip)
            node_interface_ids[node.element.get("DEVICE_ID")] = node_iface_id
        template_link = self._get_template_link("WIRELESS")
        if template_link is None:
            print("Error: Cannot create link, no template 'WIRELESS' link found.")
            return
        template_link.set("LINK_ID", str(new_link_id))
        template_link.set("LINK_NAME", str(new_link_id))
        template_link.set("DEVICE_COUNT", str(len(all_devices_on_link)))
        for dev in list(template_link.findall('DEVICE')):
            template_link.remove(dev)
        ET.SubElement(template_link, "DEVICE", {
            "DEVICE_ID": access_point.element.get("DEVICE_ID"),
            "INTERFACE_ID": str(ap_iface_id),
            "NAME": access_point.name
        })
        for node in wireless_nodes:
            dev_id = node.element.get("DEVICE_ID")
            iface_id = node_interface_ids[dev_id]
            ET.SubElement(template_link, "DEVICE", {
                "DEVICE_ID": dev_id,
                "INTERFACE_ID": str(iface_id),
                "NAME": node.name
            })
        graphics_tag = template_link.find('GRAPHICS')
        if graphics_tag is not None:
            graphics_tag.set('Name', str(new_link_id))
        self.connection_element.append(template_link)
        print(f"Successfully created Link {new_link_id} connecting {len(all_devices_on_link)} devices.")

    def create_wired_link(self, dev_a, dev_b,
                                      a_ip=None, b_ip=None, mask="255.255.255.0",
                                      link_name=None,
                                      link_speed_up="100", link_speed_down="100",
                                      err_up="1E-07", err_down="1E-07",
                                      prop_delay_up="5", prop_delay_down="5"):
        """
        Build a WIRED link between any two devices w/o templates. Also ensures Ethernet interfaces.
        """
        new_link_id = self._get_next_link_id()
        connected_to_str = f"{dev_a.name} ... {dev_b.name}"
        a_iface_id = _ensure_device_ethernet_interface_no_template(self, dev_a, connected_to_str, a_ip, mask)
        b_iface_id = _ensure_device_ethernet_interface_no_template(self, dev_b, connected_to_str, b_ip, mask)
        if a_iface_id is None or b_iface_id is None:
            print("Error: failed to create/ensure ethernet interfaces.")
            return
        link_elem = _build_wired_link_element(
            link_id=new_link_id,
            dev_a=dev_a, a_iface_id=a_iface_id,
            dev_b=dev_b, b_iface_id=b_iface_id,
            link_name=link_name,
            link_speed_up=link_speed_up, link_speed_down=link_speed_down,
            err_up=err_up, err_down=err_down,
            prop_delay_up=prop_delay_up, prop_delay_down=prop_delay_down
        )
        self.connection_element.append(link_elem)
        print(f"Successfully created WIRED Link {new_link_id} between {dev_a.name} and {dev_b.name}.")

    def _get_application_config_root(self):
        """Return the <APPLICATION_CONFIGURATION> element, create if missing."""
        app_cfg = self.root.find('.//APPLICATION_CONFIGURATION')
        if app_cfg is None:
            app_cfg = ET.Element("APPLICATION_CONFIGURATION", {"COUNT": "0"})
            # Insert before <SIMULATION_PARAMETER> if present, else append to root
            sim_param = self.root.find('.//SIMULATION_PARAMETER')
            if sim_param is not None:
                idx = list(self.root).index(sim_param)
                self.root.insert(idx, app_cfg)
            else:
                self.root.append(app_cfg)
        return app_cfg

    def _get_next_application_id(self):
        """Return next available integer ID for <APPLICATION>."""
        app_cfg = self._get_application_config_root()
        max_id = 0
        for app in app_cfg.findall('APPLICATION'):
            try:
                aid = int(app.get('ID', 0))
                if aid > max_id:
                    max_id = aid
            except ValueError:
                continue
        return max_id + 1

    def _update_application_count(self):
        """Keep APPLICATION_CONFIGURATION COUNT in sync."""
        app_cfg = self._get_application_config_root()
        count = len(app_cfg.findall('APPLICATION'))
        app_cfg.set('COUNT', str(count))

    # ---------- PUBLIC: create UNICAST CBR ----------
    def create_unicast_cbr_app(self,
                               source_device_elem,
                               destination_device_elem,
                               start_time="0",
                               end_time="100000",
                               transport="TCP",      # or "UDP"
                               generation_rate_kbps="512",
                               packet_size_bytes="1460",
                               inter_arrival_time_us="20000",
                               app_name=None):
        """
        Create a UNICAST CBR application between two devices.
        Args expect raw DEVICE ET.Elements (or anything with .get('DEVICE_ID')).
        """
        # resolve IDs
        src_id = source_device_elem.get("DEVICE_ID")
        dst_id = destination_device_elem.get("DEVICE_ID")
        if not src_id or not dst_id:
            print("Error: invalid source/destination device.")
            return None

        app_cfg = self._get_application_config_root()
        new_id = self._get_next_application_id()

        app_attrs = {
            "KEY": "Unicast_CBR",
            "APPLICATION_METHOD": "UNICAST",
            "APPLICATION_TYPE": "CBR",
            "ID": str(new_id),
            "NAME": app_name or f"App{new_id}_CBR",
            "SOURCE_COUNT": "1",
            "SOURCE_ID": str(src_id),
            "DESTINATION_COUNT": "1",
            "DESTINATION_ID": str(dst_id),
            "START_TIME": str(start_time),
            "END_TIME": str(end_time),
            "ENCRYPTION": "None",
            "RANDOM_STARTUP": "False",
            "PROTOCOL": "None",
            "TRANSPORT_PROTOCOL": transport,  # TCP/UDP
            "QOS": "BE",
            "PRIORITY": "Low",
            "GENERATION_RATE": f"{generation_rate_kbps} kbps"
        }
        app_elem = ET.Element("APPLICATION", app_attrs)

        ET.SubElement(app_elem, "PACKET_SIZE", {
            "DISTRIBUTION": "Constant",
            "VALUE": str(packet_size_bytes)
        })
        ET.SubElement(app_elem, "INTER_ARRIVAL_TIME", {
            "DISTRIBUTION": "Constant",
            "VALUE": str(inter_arrival_time_us)
        })
        ET.SubElement(app_elem, "GRAPHICS", {"Color": "#9900FF", "Width": "1"})

        app_cfg.append(app_elem)
        self._update_application_count()
        print(f"Created UNICAST CBR app ID {new_id}: {source_device_elem.get('DEVICE_NAME')} -> {destination_device_elem.get('DEVICE_NAME')}")
        return app_elem

    # ---------- PUBLIC: create MULTICAST CBR ----------
    def create_multicast_cbr_app(self,
                                 source_device_elem,
                                 destination_device_elems,  # list of DEVICE ET.Elements
                                 start_time="0",
                                 end_time="100000",
                                 transport="UDP",          # multicast usually UDP
                                 generation_rate_kbps="512",
                                 packet_size_bytes="1460",
                                 inter_arrival_time_us="20000",
                                 app_name=None):
        """
        Create a MULTICAST CBR application.
        Writes DESTINATION_COUNT and comma-separated DESTINATION_ID as per common NetSim format.
        """
        src_id = source_device_elem.get("DEVICE_ID")
        if not src_id:
            print("Error: invalid source device.")
            return None

        dst_ids = [d.get("DEVICE_ID") for d in destination_device_elems if d is not None and d.get("DEVICE_ID")]
        if not dst_ids:
            print("Error: provide at least one destination for multicast.")
            return None

        app_cfg = self._get_application_config_root()
        new_id = self._get_next_application_id()

        dest_count = str(len(dst_ids))
        dest_id_str = ",".join(dst_ids)  # minimal-change, common schema

        app_attrs = {
            "KEY": "Multicast_CBR",
            "APPLICATION_METHOD": "MULTICAST",
            "APPLICATION_TYPE": "CBR",
            "ID": str(new_id),
            "NAME": app_name or f"App{new_id}_MC_CBR",
            "SOURCE_COUNT": "1",
            "SOURCE_ID": str(src_id),
            "DESTINATION_COUNT": dest_count,
            "DESTINATION_ID": dest_id_str,
            "START_TIME": str(start_time),
            "END_TIME": str(end_time),
            "ENCRYPTION": "None",
            "RANDOM_STARTUP": "False",
            "PROTOCOL": "None",
            "TRANSPORT_PROTOCOL": transport,  # typically UDP
            "QOS": "BE",
            "PRIORITY": "Low",
            "GENERATION_RATE": f"{generation_rate_kbps} kbps"
        }
        app_elem = ET.Element("APPLICATION", app_attrs)

        ET.SubElement(app_elem, "PACKET_SIZE", {
            "DISTRIBUTION": "Constant",
            "VALUE": str(packet_size_bytes)
        })
        ET.SubElement(app_elem, "INTER_ARRIVAL_TIME", {
            "DISTRIBUTION": "Constant",
            "VALUE": str(inter_arrival_time_us)
        })
        ET.SubElement(app_elem, "GRAPHICS", {"Color": "#00AA55", "Width": "1"})

        app_cfg.append(app_elem)
        self._update_application_count()
        names = [d.get('DEVICE_NAME') for d in destination_device_elems]
        print(f"Created MULTICAST CBR app ID {new_id}: {source_device_elem.get('DEVICE_NAME')} -> {names}")
        return app_elem
    
    def delete_application(self, app_id: int = None, app_name: str = None) -> bool:
        """
        Delete an <APPLICATION> from APPLICATION_CONFIGURATION.
        Provide either app_id (int or str) or app_name (exact match).
        Returns True if deleted, False otherwise.
        """
        app_cfg = self._get_application_config_root()
        if app_cfg is None:
            print("Error: No APPLICATION_CONFIGURATION found.")
            return False

        target = None
        if app_id is not None:
            # match by ID (string-compare to be safe)
            str_id = str(app_id)
            for app in app_cfg.findall('APPLICATION'):
                if app.get('ID') == str_id:
                    target = app
                    break
        elif app_name is not None:
            for app in app_cfg.findall('APPLICATION'):
                if app.get('NAME') == app_name:
                    target = app
                    break
        else:
            print("delete_application: provide either app_id or app_name.")
            return False

        if target is None:
            print("Application not found.")
            return False

        # remove and update count
        app_cfg.remove(target)
        self._update_application_count()
        print(f"Deleted application (ID={target.get('ID')}, NAME={target.get('NAME')}).")
        return True
    
    def update_parameters_for_all_connected_clients(self, ap_name, frequency_band=None, channel_width=None, channel=None):
        """
        Updates the wireless configuration (Frequency Band, Channel Width, Channel) 
        for a specific AP and propagates changes to all connected wireless nodes.
        
        Args:
            ap_name (str): Name of the Access Point.
            frequency_band (str): e.g., "2.4", "5".
            channel_width (str): e.g., "20", "40", "80" (MHz).
            channel (str): e.g., "36", "1", "6".
        """
        # 1. Locate the AP
        target_ap = None
        for ap in self.get_all_access_points():
            if ap.name == ap_name:
                target_ap = ap
                break
        
        if not target_ap:
            print(f"Error: Access Point '{ap_name}' not found.")
            return

        print(f"\n--- Updating Wireless Config for {ap_name} ---")

        # Helper function to apply settings to a device wrapper
        def apply_changes(device_wrapper):
            # Frequency Band (e.g., "2.4" or "5")
            if frequency_band:
                device_wrapper.set_wireless_phy_param("FREQUENCY_BAND", str(frequency_band))

            # Channel Width (Attribute is 'BANDWIDTH' in NetSim XML)
            if channel_width:
                device_wrapper.set_wireless_phy_param("BANDWIDTH", str(channel_width))

            # Channel Number
            if channel:
                device_wrapper.set_wireless_phy_param("CHANNEL", str(channel))

        # 2. Update the AP
        apply_changes(target_ap)

        # 3. Find Connected Clients via Wireless Links
        links = self.get_all_links()
        connected_nodes = []
        
        for link in links:
            # We only care about wireless links
            if link.medium == "WIRELESS":
                # Check if our AP is part of this link
                link_dev_names = [d['name'] for d in link.devices]
                if ap_name in link_dev_names:
                    # Identify other devices (Nodes) in this link
                    for d_info in link.devices:
                        d_name = d_info['name']
                        # Skip the AP itself
                        if d_name != ap_name:
                            # Fetch the raw device element
                            d_elem = self.get_device_by_name(d_name)
                            if d_elem is not None and d_elem.get('TYPE') == 'NODE':
                                # Create a temporary wrapper to use the set_param methods
                                # Note: WirelessNode class must be visible in module scope
                                connected_nodes.append(WirelessNode(d_elem))

        # 4. Propagate to Clients
        if connected_nodes:
            print(f"Propagating changes to {len(connected_nodes)} connected clients...")
            for node in connected_nodes:
                print(f"  -> Updating {node.name}")
                apply_changes(node)
        else:
            print("No connected wireless clients found to update.")
            
        print("Update complete.")

# =========================
# Device Wrappers (existing)
# =========================
class AccessPoint:
    def __init__(self, device_element):
        self.element = device_element
        self.name = self.element.get('DEVICE_NAME')
        self.pos_3d = self.element.find('POS_3D')
        self._initialize_interfaces()

    def _initialize_interfaces(self):
        self.wireless_interface = None
        for iface in self.element.findall('INTERFACE'):
            if iface.get('INTERFACE_TYPE') == 'WIRELESS':
                self.wireless_interface = iface
                break
        self.ethernet_interface = None
        for iface in self.element.findall('INTERFACE'):
            if iface.get('INTERFACE_TYPE') == 'ETHERNET':
                self.ethernet_interface = iface
                break
        if self.wireless_interface is None:
            self.datalink_props = None
            self.phy_props = None
            self.antenna_props = None
        else:
            self.datalink_props = self.wireless_interface.find(
                './/LAYER[@TYPE="DATALINK_LAYER"]//PROTOCOL[@NAME="IEEE802.11"]/PROTOCOL_PROPERTY'
            )
            self.phy_props = self.wireless_interface.find(
                './/LAYER[@TYPE="PHYSICAL_LAYER"]//PROTOCOL[@NAME="IEEE802.11"]/PROTOCOL_PROPERTY'
            )
            self.antenna_props = self.phy_props.find('ANTENNA') if self.phy_props is not None else None
        if self.ethernet_interface is None:
            self.eth_datalink_props = None
            self.eth_phy_props = None
        else:
            self.eth_datalink_props = self.ethernet_interface.find(
                './/LAYER[@TYPE="DATALINK_LAYER"]//PROTOCOL[@NAME="ETHERNET"]/PROTOCOL_PROPERTY'
            )
            self.eth_phy_props = self.ethernet_interface.find(
                './/LAYER[@TYPE="PHYSICAL_LAYER"]//PROTOCOL[@NAME="ETHERNET"]/PROTOCOL_PROPERTY'
            )

    def ensure_wireless_interface(self, config_manager, connected_to_str):
        if self.wireless_interface is not None:
            print(f"  Updating existing wireless interface on {self.name}...")
            if self.phy_props is not None:
                self.phy_props.set("CONNECTED_TO", connected_to_str)
                return self.wireless_interface.get("ID")
            else:
                print(f"  Error: Could not find PHY properties for existing interface on {self.name}")
                return self.wireless_interface.get("ID")
        print(f"  Creating new wireless interface for {self.name}...")
        new_iface_id = config_manager._get_next_interface_id(self.element)
        template_iface = config_manager._get_template_interface("ACCESSPOINT", "WIRELESS")
        if template_iface is None:
            print(f"  FATAL: Could not create interface for {self.name}, no template found.")
            return None
        device_id = self.element.get("DEVICE_ID")
        new_mac = config_manager._generate_mac(device_id, new_iface_id)
        template_iface.set("ID", str(new_iface_id))
        template_iface.set("INTERFACE_NAME", f"Interface_{new_iface_id} (Wireless)")
        dl_props = template_iface.find('.//LAYER[@TYPE="DATALINK_LAYER"]//PROTOCOL_PROPERTY')
        if dl_props is not None:
            dl_props.set("MAC_ADDRESS", new_mac)
            print(f"    Set MAC: {new_mac}")
        phy_props = template_iface.find('.//LAYER[@TYPE="PHYSICAL_LAYER"]//PROTOCOL_PROPERTY')
        if phy_props is not None:
            phy_props.set("CONNECTED_TO", connected_to_str)
        self.element.append(template_iface)
        self._initialize_interfaces()
        return new_iface_id

    def get_name(self):
        return self.element.get('DEVICE_NAME')

    def set_name(self, name):
        self.element.set('DEVICE_NAME', name)
        self.name = name
        print(f"Set {self.name} DEVICE_NAME to '{name}'")

    def get_position(self):
        if self.pos_3d is not None:
            return self.pos_3d.attrib
        return {}

    def set_position(self, x=None, y=None, z=None):
        if self.pos_3d is not None:
            if x is not None:
                self.pos_3d.set('X_OR_LON', str(x))
                print(f"Set {self.name} X_OR_LON to '{x}'")
            if y is not None:
                self.pos_3d.set('Y_OR_LAT', str(y))
                print(f"Set {self.name} Y_OR_LAT to '{y}'")
            if z is not None:
                self.pos_3d.set('Z', str(z))
                print(f"Set {self.name} Z to '{z}'")
        else:
            print(f"Error: Could not find POS_3D for {self.name}")

    def _get_params(self, element):
        if element is not None:
            return element.attrib
        return {}

    def _set_param(self, element, param, value):
        if element is not None:
            if param in element.attrib:
                element.set(param, str(value))
                print(f"Set {self.name} {param} to '{value}'")
                return True
            else:
                return False
        else:
            return False

    def get_wireless_datalink_params(self):
        return self._get_params(self.datalink_props)

    def set_wireless_datalink_param(self, param, value):
        return self._set_param(self.datalink_props, param, value)

    def get_wireless_phy_params(self):
        return self._get_params(self.phy_props)

    def set_wireless_phy_param(self, param, value):
        return self._set_param(self.phy_props, param, value)

    def get_antenna_params(self):
        return self._get_params(self.antenna_props)

    def set_antenna_param(self, param, value):
        return self._set_param(self.antenna_props, param, value)

    def get_ethernet_datalink_params(self):
        return self._get_params(self.eth_datalink_props)

    def set_ethernet_datalink_param(self, param, value):
        return self._set_param(self.eth_datalink_props, param, value)

    def get_ethernet_phy_params(self):
        return self._get_params(self.eth_phy_props)

    def set_ethernet_phy_param(self, param, value):
        return self._set_param(self.eth_phy_props, param, value)

    def show_all_params(self):
        print(f"\n--- Parameters for {self.name} ---")
        print("\n[Device]")
        print(f"  DEVICE_NAME: {self.get_name()}")
        print("\n[Position (POS_3D)]")
        pos_params = self.get_position()
        if pos_params:
            for key, val in pos_params.items():
                print(f"  {key}: {val}")
        else:
            print("  (No position info)")
        if self.wireless_interface is not None:
            iface_name = self.wireless_interface.get('INTERFACE_NAME', 'Wireless')
            datalink_params = self.get_wireless_datalink_params()
            if datalink_params:
                print(f"\n[{iface_name} Datalink (IEEE802.11)]")
                for key, val in datalink_params.items():
                    print(f"  {key}: {val}")
            phy_params = self.get_wireless_phy_params()
            if phy_params:
                print(f"\n[{iface_name} Physical (IEEE802.11)]")
                if self.antenna_props is not None and self.antenna_props.tag in phy_params:
                    phy_params.pop(self.antenna_props.tag)
                for key, val in phy_params.items():
                    print(f"  {key}: {val}")
            antenna_params = self.get_antenna_params()
            if antenna_params:
                print(f"\n[{iface_name} Antenna (ANTENNA)]")
                for key, val in antenna_params.items():
                    print(f"  {key}: {val}")
        else:
            print("\n[Wireless Interface]")
            print("  (No wireless interface found or configured)")
        if self.ethernet_interface is not None:
            iface_name = self.ethernet_interface.get('INTERFACE_NAME', 'Ethernet')
            eth_datalink_params = self.get_ethernet_datalink_params()
            if eth_datalink_params:
                print(f"\n[{iface_name} Datalink (ETHERNET)]")
                for key, val in eth_datalink_params.items():
                    print(f"  {key}: {val}")
            eth_phy_params = self.get_ethernet_phy_params()
            if eth_phy_params:
                print(f"\n[{iface_name} Physical (ETHERNET)]")
                for key, val in eth_phy_params.items():
                    print(f"  {key}: {val}")
        else:
            print("\n[Ethernet Interface]")
            print("  (No ethernet interface found or configured)")
        print("----------------------------------")

    def edit_parameter(self, param_name, param_value):
        if param_name == 'DEVICE_NAME':
            self.set_name(param_value)
            return
        if param_name in self.get_position():
            kwargs = {param_name.lower(): param_value}
            if 'x_or_lon' in kwargs: kwargs['x'] = kwargs.pop('x_or_lon')
            if 'y_or_lat' in kwargs: kwargs['y'] = kwargs.pop('y_or_lat')
            if 'z' in kwargs: kwargs['z'] = kwargs.pop('z')
            self.set_position(**kwargs)
            return
        if self.set_wireless_datalink_param(param_name, param_value): return
        if self.set_wireless_phy_param(param_name, param_value): return
        if self.set_antenna_param(param_name, param_value): return
        if self.set_ethernet_datalink_param(param_name, param_value): return
        if self.set_ethernet_phy_param(param_name, param_value): return
        print(f"Error: Parameter '{param_name}' was not found or is not editable.")


class RouterInterface:
    def __init__(self, interface_element, router_name):
        self.element = interface_element
        self.id = self.element.get('ID')
        self.name = self.element.get('INTERFACE_NAME')
        self.router_name = router_name
        self.net_props_ipv4 = self.element.find(
            './/LAYER[@TYPE="NETWORK_LAYER"]//NETWORK_PROTOCOL[@NAME="IPV4"]/PROTOCOL_PROPERTY'
        )
        self.net_props_arp = self.element.find(
            './/LAYER[@TYPE="NETWORK_LAYER"]//PROTOCOL[@NAME="ARP"]/PROTOCOL_PROPERTY'
        )
        self.datalink_props = self.element.find(
            './/LAYER[@TYPE="DATALINK_LAYER"]//PROTOCOL[@NAME="ETHERNET"]/PROTOCOL_PROPERTY'
        )
        self.phy_props = self.element.find(
            './/LAYER[@TYPE="PHYSICAL_LAYER"]//PROTOCOL[@NAME="ETHERNET"]/PROTOCOL_PROPERTY'
        )

    def _get_params(self, element):
        if element is not None:
            return element.attrib
        return {}

    def _set_param(self, element, param, value):
        if element is not None:
            if param in element.attrib:
                element.set(param, str(value))
                print(f"Set {self.router_name} (Iface {self.id}) {param} to '{value}'")
                return True
        return False

    def get_net_ipv4_params(self): return self._get_params(self.net_props_ipv4)
    def get_net_arp_params(self): return self._get_params(self.net_props_arp)
    def get_datalink_params(self): return self._get_params(self.datalink_props)
    def get_phy_params(self): return self._get_params(self.phy_props)

    def set_net_ipv4_param(self, param, value): return self._set_param(self.net_props_ipv4, param, value)
    def set_net_arp_param(self, param, value): return self._set_param(self.net_props_arp, param, value)
    def set_datalink_param(self, param, value): return self._set_param(self.datalink_props, param, value)
    def set_phy_param(self, param, value): return self._set_param(self.phy_props, param, value)


class Router:
    def __init__(self, device_element):
        self.element = device_element
        self.name = self.element.get('DEVICE_NAME')
        self.pos_3d = self.element.find('POS_3D')
        self.app_layer_openflow = self.element.find(
            './LAYER[@TYPE="APPLICATION_LAYER"]//PROTOCOL[@NAME="OPEN_FLOW"]/PROTOCOL_PROPERTY'
        )
        self.app_layer_ospf = self.element.find(
            './LAYER[@TYPE="APPLICATION_LAYER"]//ROUTING_PROTOCOL[@NAME="OSPF"]/PROTOCOL_PROPERTY'
        )
        self.transport_tcp = self.element.find(
            './LAYER[@TYPE="TRANSPORT_LAYER"]//PROTOCOL[@NAME="TCP"]/PROTOCOL_PROPERTY'
        )
        self.transport_udp = self.element.find(
            './LAYER[@TYPE="TRANSPORT_LAYER"]//PROTOCOL[@NAME="UDP"]/PROTOCOL_PROPERTY'
        )
        self.network_ipv4 = self.element.find(
            './LAYER[@TYPE="NETWORK_LAYER"]//PROTOCOL[@NAME="IPV4"]/PROTOCOL_PROPERTY'
        )
        self.interfaces = []
        for iface_elem in self.element.findall('INTERFACE'):
            self.interfaces.append(RouterInterface(iface_elem, self.name))

    def get_name(self): return self.element.get('DEVICE_NAME')

    def set_name(self, name):
        self.element.set('DEVICE_NAME', name)
        self.name = name
        print(f"Set {self.name} DEVICE_NAME to '{name}'")

    def get_position(self):
        if self.pos_3d is not None:
            return self.pos_3d.attrib
        return {}

    def set_position(self, x=None, y=None, z=None):
        if self.pos_3d is not None:
            if x is not None: self.pos_3d.set('X_OR_LON', str(x))
            if y is not None: self.pos_3d.set('Y_OR_LAT', str(y))
            if z is not None: self.pos_3d.set('Z', str(z))
            print(f"Set {self.name} position.")
        else:
            print(f"Error: Could not find POS_3D for {self.name}")

    def _get_params(self, element):
        if element is not None:
            return element.attrib
        return {}

    def _set_param(self, element, param, value):
        if element is not None:
            if param in element.attrib:
                element.set(param, str(value))
                print(f"Set {self.name} {param} to '{value}'")
                return True
        return False

    def get_app_openflow_params(self): return self._get_params(self.app_layer_openflow)
    def set_app_openflow_param(self, p, v): return self._set_param(self.app_layer_openflow, p, v)
    def get_ospf_params(self): return self._get_params(self.app_layer_ospf)
    def set_ospf_param(self, p, v): return self._set_param(self.app_layer_ospf, p, v)
    def get_transport_tcp_params(self): return self._get_params(self.transport_tcp)
    def set_transport_tcp_param(self, p, v): return self._set_param(self.transport_tcp, p, v)
    def get_transport_udp_params(self): return self._get_params(self.transport_udp)
    def set_transport_udp_param(self, p, v): return self._set_param(self.transport_udp, p, v)
    def get_network_ipv4_params(self): return self._get_params(self.network_ipv4)
    def set_network_ipv4_param(self, p, v): return self._set_param(self.network_ipv4, p, v)

    def show_all_params(self):
        print(f"\n--- Parameters for {self.name} ---")
        print("\n[Device]")
        print(f"  DEVICE_NAME: {self.get_name()}")
        print("\n[Position (POS_3D)]")
        for k, v in self.get_position().items(): print(f"  {k}: {v}")
        print("\n[Device Application Layer (OPEN_FLOW)]")
        for k, v in self.get_app_openflow_params().items(): print(f"  {k}: {v}")
        print("\n[Device Application Layer (OSPF)]")
        for k, v in self.get_ospf_params().items(): print(f"  {k}: {v}")
        print("\n[Device Transport Layer (TCP)]")
        for k, v in self.get_transport_tcp_params().items(): print(f"  {k}: {v}")
        print("\n[Device Transport Layer (UDP)]")
        for k, v in self.get_transport_udp_params().items(): print(f"  {k}: {v}")
        print("\n[Device Network Layer (IPV4)]")
        for k, v in self.get_network_ipv4_params().items(): print(f"  {k}: {v}")
        print("\n--- Interfaces ---")
        if not self.interfaces:
            print("  (No interfaces configured)")
        for iface in self.interfaces:
            print(f"\n[Interface ID: {iface.id} ({iface.name})]")
            print("  [Network (IPV4)]")
            for k, v in iface.get_net_ipv4_params().items(): print(f"    {k}: {v}")
            print("  [Network (ARP)]")
            for k, v in iface.get_net_arp_params().items(): print(f"    {k}: {v}")
            print("  [Datalink (ETHERNET)]")
            for k, v in iface.get_datalink_params().items(): print(f"    {k}: {v}")
            print("  [Physical (ETHERNET)]")
            for k, v in iface.get_phy_params().items(): print(f"    {k}: {v}")
        print("----------------------------------")

    def edit_parameter(self, param_name, param_value, interface_id=None):
        if param_name == 'DEVICE_NAME':
            self.set_name(param_value); return
        if param_name in self.get_position():
            kwargs = {param_name.lower(): param_value}
            if 'x_or_lon' in kwargs: kwargs['x'] = kwargs.pop('x_or_lon')
            if 'y_or_lat' in kwargs: kwargs['y'] = kwargs.pop('y_or_lat')
            if 'z' in kwargs: kwargs['z'] = kwargs.pop('z')
            self.set_position(**kwargs); return
        if interface_id is None:
            if self.set_app_openflow_param(param_name, param_value): return
            if self.set_ospf_param(param_name, param_value): return
            if self.set_transport_tcp_param(param_name, param_value): return
            if self.set_transport_udp_param(param_name, param_value): return
            if self.set_network_ipv4_param(param_name, param_value): return
        if interface_id is not None:
            iface_to_edit = None
            for iface in self.interfaces:
                if iface.id == interface_id: iface_to_edit = iface; break
            if iface_to_edit:
                if iface_to_edit.set_net_ipv4_param(param_name, param_value): return
                if iface_to_edit.set_net_arp_param(param_name, param_value): return
                if iface_to_edit.set_datalink_param(param_name, param_value): return
                if iface_to_edit.set_phy_param(param_name, param_value): return
            else:
                print(f"Error: Interface ID '{interface_id}' not found."); return
        print(f"Error: Parameter '{param_name}' was not found or is not editable.")
        if interface_id is None:
            print("  (Note: For interface params like IP_ADDRESS, provide Interface ID.)")


class WirelessNode:
    def __init__(self, device_element):
        self.element = device_element
        self.name = self.element.get('DEVICE_NAME')
        self.pos_3d = self.element.find('POS_3D')
        self._initialize_interfaces()

    def _initialize_interfaces(self):
        self.wireless_interface = None
        for iface in self.element.findall('INTERFACE'):
            if iface.get('INTERFACE_TYPE') == 'WIRELESS':
                self.wireless_interface = iface; break
        if self.wireless_interface is None:
            self.wl_net_props_ipv4 = None
            self.wl_net_props_arp = None
            self.wl_datalink_props = None
            self.wl_phy_props = None
            self.wl_antenna_props = None
        else:
            self.wl_net_props_ipv4 = self.wireless_interface.find(
                './/LAYER[@TYPE="NETWORK_LAYER"]//NETWORK_PROTOCOL[@NAME="IPV4"]/PROTOCOL_PROPERTY'
            )
            self.wl_net_props_arp = self.wireless_interface.find(
                './/LAYER[@TYPE="NETWORK_LAYER"]//PROTOCOL[@NAME="ARP"]/PROTOCOL_PROPERTY'
            )
            self.wl_datalink_props = self.wireless_interface.find(
                './/LAYER[@TYPE="DATALINK_LAYER"]//PROTOCOL[@NAME="IEEE802.11"]/PROTOCOL_PROPERTY'
            )
            self.wl_phy_props = self.wireless_interface.find(
                './/LAYER[@TYPE="PHYSICAL_LAYER"]//PROTOCOL[@NAME="IEEE802.11"]/PROTOCOL_PROPERTY'
            )
            self.wl_antenna_props = self.wl_phy_props.find('ANTENNA') if self.wl_phy_props is not None else None
        self.app_layer_openflow = self.element.find(
            './LAYER[@TYPE="APPLICATION_LAYER"]//PROTOCOL[@NAME="OPEN_FLOW"]/PROTOCOL_PROPERTY'
        )
        self.transport_tcp = self.element.find(
            './LAYER[@TYPE="TRANSPORT_LAYER"]//PROTOCOL[@NAME="TCP"]/PROTOCOL_PROPERTY'
        )
        self.transport_udp = self.element.find(
            './LAYER[@TYPE="TRANSPORT_LAYER"]//PROTOCOL[@NAME="UDP"]/PROTOCOL_PROPERTY'
        )
        self.network_ipv4 = self.element.find(
            './LAYER[@TYPE="NETWORK_LAYER"]//PROTOCOL[@NAME="IPV4"]/PROTOCOL_PROPERTY'
        )

    def ensure_wireless_interface(self, config_manager, connected_to_str, ip, subnet_mask, gateway):
        if self.wireless_interface is not None:
            print(f"  Updating existing wireless interface on {self.name}...")
            if self.wl_net_props_ipv4 is not None:
                self.wl_net_props_ipv4.set("IP_ADDRESS", ip)
                self.wl_net_props_ipv4.set("SUBNET_MASK", subnet_mask)
                self.wl_net_props_ipv4.set("DEFAULT_GATEWAY", gateway)
                print(f"    Set IP: {ip}")
            if self.wl_phy_props is not None:
                self.wl_phy_props.set("CONNECTED_TO", connected_to_str)
            else:
                print(f"  Error: Could not find PHY properties for existing interface on {self.name}")
            return self.wireless_interface.get("ID")
        print(f"  Creating new wireless interface for {self.name}...")
        new_iface_id = config_manager._get_next_interface_id(self.element)
        template_iface = config_manager._get_template_interface("NODE", "WIRELESS")
        if template_iface is None:
            print(f"  FATAL: Could not create interface for {self.name}, no template found.")
            return None
        device_id = self.element.get("DEVICE_ID")
        new_mac = config_manager._generate_mac(device_id, new_iface_id)
        template_iface.set("ID", str(new_iface_id))
        template_iface.set("INTERFACE_NAME", f"Interface_{new_iface_id} (Wireless)")
        net_props = template_iface.find('.//LAYER[@TYPE="NETWORK_LAYER"]//NETWORK_PROTOCOL[@NAME="IPV4"]/PROTOCOL_PROPERTY')
        if net_props is not None:
            net_props.set("IP_ADDRESS", ip)
            net_props.set("SUBNET_MASK", subnet_mask)
            net_props.set("DEFAULT_GATEWAY", gateway)
            print(f"    Set IP: {ip}")
        dl_props = template_iface.find('.//LAYER[@TYPE="DATALINK_LAYER"]//PROTOCOL_PROPERTY')
        if dl_props is not None:
            dl_props.set("MAC_ADDRESS", new_mac)
            print(f"    Set MAC: {new_mac}")
        phy_props = template_iface.find('.//LAYER[@TYPE="PHYSICAL_LAYER"]//PROTOCOL_PROPERTY')
        if phy_props is not None:
            phy_props.set("CONNECTED_TO", connected_to_str)
        self.element.append(template_iface)
        self._initialize_interfaces()
        return new_iface_id

    def get_name(self): return self.element.get('DEVICE_NAME')

    def set_name(self, name):
        self.element.set('DEVICE_NAME', name); self.name = name
        print(f"Set {self.name} DEVICE_NAME to '{name}'")

    def get_position(self):
        if self.pos_3d is not None: return self.pos_3d.attrib
        return {}

    def set_position(self, x=None, y=None, z=None):
        if self.pos_3d is not None:
            if x is not None:
                self.pos_3d.set('X_OR_LON', str(x)); print(f"Set {self.name} X_OR_LON to '{x}'")
            if y is not None:
                self.pos_3d.set('Y_OR_LAT', str(y)); print(f"Set {self.name} Y_OR_LAT to '{y}'")
            if z is not None:
                self.pos_3d.set('Z', str(z)); print(f"Set {self.name} Z to '{z}'")
        else:
            print(f"Error: Could not find POS_3D for {self.name}")

    def _get_params(self, element):
        if element is not None: return element.attrib
        return {}

    def _set_param(self, element, param, value):
        if element is not None:
            if param in element.attrib:
                element.set(param, str(value)); print(f"Set {self.name} {param} to '{value}'"); return True
        return False

    def get_wl_net_ipv4_params(self): return self._get_params(self.wl_net_props_ipv4)
    def set_wl_net_ipv4_param(self, p, v): return self._set_param(self.wl_net_props_ipv4, p, v)
    def get_wl_net_arp_params(self): return self._get_params(self.wl_net_props_arp)
    def set_wl_net_arp_param(self, p, v): return self._set_param(self.wl_net_props_arp, p, v)
    def get_wl_datalink_params(self): return self._get_params(self.wl_datalink_props)
    def set_wl_datalink_param(self, p, v): return self._set_param(self.wl_datalink_props, p, v)
    def get_wl_phy_params(self): return self._get_params(self.wl_phy_props)
    def set_wireless_phy_param(self, p, v): return self._set_param(self.wl_phy_props, p, v)
    def get_wl_antenna_params(self): return self._get_params(self.wl_antenna_props)
    def set_wl_antenna_param(self, p, v): return self._set_param(self.wl_antenna_props, p, v)
    def get_app_openflow_params(self): return self._get_params(self.app_layer_openflow)
    def set_app_openflow_param(self, p, v): return self._set_param(self.app_layer_openflow, p, v)
    def get_transport_tcp_params(self): return self._get_params(self.transport_tcp)
    def set_transport_tcp_param(self, p, v): return self._set_param(self.transport_tcp, p, v)
    def get_transport_udp_params(self): return self._get_params(self.transport_udp)
    def set_transport_udp_param(self, p, v): return self._set_param(self.transport_udp, p, v)
    def get_network_ipv4_params(self): return self._get_params(self.network_ipv4)
    def set_network_ipv4_param(self, p, v): return self._set_param(self.network_ipv4, p, v)

    def show_all_params(self):
        print(f"\n--- Parameters for {self.name} ---")
        print("\n[Device]")
        print(f"  DEVICE_NAME: {self.get_name()}")
        print("\n[Position (POS_3D)]")
        pos_params = self.get_position()
        if pos_params:
            for key, val in pos_params.items():
                print(f"  {key}: {val}")
        else:
            print("  (No position info)")
        if self.wireless_interface is not None:
            iface_name = self.wireless_interface.get('INTERFACE_NAME', 'Wireless')
            print(f"\n[{iface_name} Network (IPV4)]")
            for k, v in self.get_wl_net_ipv4_params().items(): print(f"  {k}: {v}")
            print(f"\n[{iface_name} Network (ARP)]")
            for k, v in self.get_wl_net_arp_params().items(): print(f"  {k}: {v}")
            print(f"\n[{iface_name} Datalink (IEEE802.11)]")
            for k, v in self.get_wl_datalink_params().items(): print(f"  {k}: {v}")
            print(f"\n[{iface_name} Physical (IEEE802.11)]")
            phy_params = self.get_wl_phy_params()
            if self.wl_antenna_props is not None and self.wl_antenna_props.tag in phy_params:
                phy_params.pop(self.wl_antenna_props.tag)
            for k, v in phy_params.items(): print(f"  {k}: {v}")
            print(f"\n[{iface_name} Antenna (ANTENNA)]")
            for k, v in self.get_wl_antenna_params().items(): print(f"  {k}: {v}")
        else:
            print("\n[Wireless Interface]")
            print("  (No wireless interface found or configured)")
        print("\n[Device Application Layer (OPEN_FLOW)]")
        for key, val in self.get_app_openflow_params().items(): print(f"  {key}: {val}")
        print("\n[Device Transport Layer (TCP)]")
        for key, val in self.get_transport_tcp_params().items(): print(f"  {key}: {val}")
        print("\n[Device Transport Layer (UDP)]")
        for key, val in self.get_transport_udp_params().items(): print(f"  {key}: {val}")
        print("\n[Device Network Layer (IPV4)]")
        for key, val in self.get_network_ipv4_params().items(): print(f"  {key}: {val}")
        print("----------------------------------")

    def edit_parameter(self, param_name, param_value):
        if param_name == 'DEVICE_NAME':
            self.set_name(param_value); return
        if param_name in self.get_position():
            kwargs = {param_name.lower(): param_value}
            if 'x_or_lon' in kwargs: kwargs['x'] = kwargs.pop('x_or_lon')
            if 'y_or_lat' in kwargs: kwargs['y'] = kwargs.pop('y_or_lat')
            if 'z' in kwargs: kwargs['z'] = kwargs.pop('z')
            self.set_position(**kwargs); return
        if self.set_wl_net_ipv4_param(param_name, param_value): return
        if self.set_wl_net_arp_param(param_name, param_value): return
        if self.set_wl_datalink_param(param_name, param_value): return
        if self.set_wireless_phy_param(param_name, param_value): return
        if self.set_wl_antenna_param(param_name, param_value): return
        if self.set_app_openflow_param(param_name, param_value): return
        if self.set_transport_tcp_param(param_name, param_value): return
        if self.set_transport_udp_param(param_name, param_value): return
        if self.set_network_ipv4_param(param_name, param_value): return
        print(f"Error: Parameter '{param_name}' was not found or is not editable.")
    
##################################################################################################################################
class Link:
    def __init__(self, link_element):
        self.element = link_element
        self.link_id = self.element.get('LINK_ID')
        self.name = self.element.get('LINK_NAME')
        self.type = self.element.get('TYPE')
        self.medium = self.element.get('MEDIUM')
        self.devices = []
        for dev in self.element.findall('DEVICE'):
            self.devices.append({
                "name": dev.get('NAME'),
                "id": dev.get('DEVICE_ID'),
                "iface_id": dev.get('INTERFACE_ID')
            })

    def get_connected_devices_str(self):
        return ", ".join([d['name'] for d in self.devices])
    
def get_all_device_elements(config: "NetSimConfig"):
    """
    Return list of raw <DEVICE> ET.Elements (any type).
    Useful for app creation where only DEVICE_ID/NAME are needed.
    """
    devs = []
    if config.device_config_element is not None:
        for d in config.device_config_element.findall('DEVICE'):
            devs.append(d)
    return devs

# ========= APP CREATION WIZARDS (OUTSIDE CLASSES) =========
def wizard_create_unicast_cbr(config: "NetSimConfig"):
    print("\n=== Create Application: Unicast CBR ===")
    devices = get_all_device_elements(config)
    if len(devices) < 2:
        print("Need at least two devices.")
        return

    # list devices
    for i, d in enumerate(devices, 1):
        print(f"  {i}. {d.get('DEVICE_NAME')}  [TYPE={d.get('TYPE')}, KEY={d.get('KEY')}]")

    # pick source
    try:
        s = int(input("Source #: ")) - 1
        if not (0 <= s < len(devices)): print("Invalid"); return
        src = devices[s]
    except ValueError:
        print("Invalid"); return

    # pick destination
    try:
        d_i = int(input("Destination #: ")) - 1
        if not (0 <= d_i < len(devices)) or d_i == s: print("Invalid"); return
        dst = devices[d_i]
    except ValueError:
        print("Invalid"); return

    # params
    name  = None
    start =  "0"
    end   =  "100000"
    txp   = (input("Transport (TCP/UDP, default TCP): ").strip() or "TCP").upper()
    rate  = "512"
    psize = "1460"
    iat   =  "20000"

    config.create_unicast_cbr_app(
        src, dst,
        start_time=start, end_time=end,
        transport=txp,
        generation_rate_kbps=rate,
        packet_size_bytes=psize,
        inter_arrival_time_us=iat,
        app_name=name
    )

def wizard_create_multicast_cbr(config: "NetSimConfig"):
    print("\n=== Create Application: Multicast CBR ===")
    devices = get_all_device_elements(config)
    if len(devices) < 2:
        print("Need at least two devices.")
        return

    # list devices
    for i, d in enumerate(devices, 1):
        print(f"  {i}. {d.get('DEVICE_NAME')}  [TYPE={d.get('TYPE')}, KEY={d.get('KEY')}]")

    # pick source
    try:
        s = int(input("Source #: ")) - 1
        if not (0 <= s < len(devices)): print("Invalid"); return
        src = devices[s]
    except ValueError:
        print("Invalid"); return

    # pick multiple destinations
    dest_str = input("Destination #s (comma-separated, e.g., 2,3,5): ").strip()
    try:
        idxs = sorted(set(int(x.strip()) - 1 for x in dest_str.split(",") if x.strip()))
    except ValueError:
        print("Invalid list"); return
    dests = []
    for i in idxs:
        if 0 <= i < len(devices) and i != s:
            dests.append(devices[i])
    if not dests:
        print("No valid destinations.")
        return

    # params
    name  = None
    start = "0"
    end   = "100000"
    # multicast is typically UDP
    txp   = (input("Transport (UDP recommended; default UDP): ").strip() or "UDP").upper()
    rate  = "512"
    psize = "1460"
    iat   =  "20000"

    config.create_multicast_cbr_app(
        src, dests,
        start_time=start, end_time=end,
        transport=txp,
        generation_rate_kbps=rate,
        packet_size_bytes=psize,
        inter_arrival_time_us=iat,
        app_name=name
    )

import subprocess

def run_netsim_cli(
    iopath,
    license_path,
    netsimcore_exe=r"C:\Program Files\NetSim\Standard_v14_4\bin\bin_x64\NetSimCore.exe",
    apppath=r"C:\Program Files\NetSim\Standard_v14_4\bin\bin_x64",
    show_cmd=False,
    timeout=None
):
    """
    Launch NetSimCore.exe from the command line (headless).
    Returns (exit_code, stdout, stderr).
    """
    print("\n=== Run NetSim (headless) ===")

    cmd = fr'"{netsimcore_exe}" -apppath "{apppath}" -iopath "{iopath}" -license "{license_path}"'
    if show_cmd:
        print("Running:", cmd)

    # Hide the spawned window on Windows
    startupinfo = None
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    except Exception:
        pass

    # Run
    proc = subprocess.run(
        cmd,
        shell=True,              # needed for the quoted string on Windows
        capture_output=True,
        text=True,
        timeout=timeout,
        startupinfo=startupinfo
    )
    # Show concise summary
    print(f"[NetSim] exit code: {proc.returncode}")
    if proc.stdout:
        print("----- stdout -----")
        print(proc.stdout.strip())
    if proc.stderr:
        print("----- stderr -----")
        print(proc.stderr.strip())
        # Run ThroughputCalculator if log_csv_path is provided
    log_csv_path = os.path.join(os.path.abspath(iopath), "log", "Link_Packet_Log.csv")
    throughput_calculator_exe = r"C:\Program Files\NetSim\Standard_v14_4\Docs\Advanced_PlotScripts\Application_Packet_Log\ThroughputCalculator.exe"
    if log_csv_path and os.path.exists(log_csv_path):
        print(f"\n=== Run ThroughputCalculator ===")
        calc_cmd = fr'"{throughput_calculator_exe}" "{log_csv_path}" 50'
        if show_cmd:
            print("Running:", calc_cmd)
        
        try:
            calc_proc = subprocess.run(
                calc_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                startupinfo=startupinfo
            )
            print(f"[ThroughputCalculator] exit code: {calc_proc.returncode}")
            if calc_proc.stdout:
                print("----- Calculator stdout -----")
                print(calc_proc.stdout.strip())
            if calc_proc.stderr:
                print("----- Calculator stderr -----")
                print(calc_proc.stderr.strip())
            return calc_proc.returncode, calc_proc.stdout, calc_proc.stderr
        except subprocess.TimeoutExpired:
            print("[ThroughputCalculator] Timed out.")
            return -1, "", "Timeout"
        except Exception as e:
            print(f"[ThroughputCalculator] Error: {e}")
            return -1, "", str(e)
    elif log_csv_path:
        print(f"[ThroughputCalculator] Log file not found: {log_csv_path}")
    
    return proc.returncode, proc.stdout, proc.stderr

# =========================
# UI Helpers (modular)
# =========================
def list_access_points(config):
    print("\n--- Available Access Points ---")
    aps = config.get_all_access_points()
    if not aps:
        print("No Access Points found in the configuration.")
        return False
    for i, ap in enumerate(aps):
        print(f"  {i+1}. {ap.name}")
    return True

def select_ap_menu(config):
    aps = config.get_all_access_points()
    if not aps:
        print("No Access Points found to edit.")
        return
    list_access_points(config)
    try:
        choice = int(input("Enter the number of the AP to edit: "))
        if 0 < choice <= len(aps):
            selected_ap = aps[choice - 1]
            edit_ap_menu(selected_ap)
        else:
            print("Invalid number.")
    except ValueError:
        print("Invalid input. Please enter a number.")

def edit_ap_menu(ap):
    while True:
        print(f"\n--- Editing {ap.name} ---")
        print("1. View All Parameters")
        print("2. Edit a Parameter")
        print("3. Back to Main Menu")
        choice = input("Enter yourchoice (1-3): ")
        if choice == '1':
            ap.show_all_params()
        elif choice == '2':
            param_name = input("Enter the exact parameter name to edit (e.g., 'TX_POWER'): ")
            param_value = input(f"Enter the new value for '{param_name}': ")
            ap.edit_parameter(param_name, param_value)
        elif choice == '3':
            break
        else:
            print("Invalid choice.")

def list_links(config):
    print("\n--- Available Links ---")
    links = config.get_all_links()
    if not links:
        print("No Links found in the configuration.")
        return False
    for i, link in enumerate(links):
        devices_str = link.get_connected_devices_str()
        print(f"  {i+1}. ID: {link.link_id} (Name: {link.name}, Type: {link.medium}/{link.type})")
        print(f"     Connects: {devices_str}")
    return True

def list_routers(config):
    print("\n--- Available Routers ---")
    routers = config.get_all_routers()
    if not routers:
        print("No Routers found in the configuration.")
        return False
    for i, router in enumerate(routers):
        print(f"  {i+1}. {router.name}")
    return True

def select_router_menu(config):
    routers = config.get_all_routers()
    if not routers:
        print("No Routers found to edit.")
        return
    list_routers(config)
    try:
        choice = int(input("Enter the number of the Router to edit: "))
        if 0 < choice <= len(routers):
            selected_router = routers[choice - 1]
            edit_router_menu(selected_router)
        else:
            print("Invalid number.")
    except ValueError:
        print("Invalid input. Please enter a number.")

def edit_router_menu(router):
    while True:
        print(f"\n--- Editing {router.name} ---")
        print("1. View All Parameters")
        print("2. Edit a Parameter")
        print("3. Back to Main Menu")
        choice = input("Enter your choice (1-3): ")
        if choice == '1':
            router.show_all_params()
        elif choice == '2':
            param_name = input("Enter the exact parameter name to edit (e.g., 'IP_ADDRESS', 'VERSION'): ")
            param_value = input(f"Enter the new value for '{param_name}': ")
            iface_id = input("Enter Interface ID to edit (e.g., '1', or leave blank for device-level param): ")
            if iface_id.strip() == "": iface_id = None
            router.edit_parameter(param_name, param_value, interface_id=iface_id)
        elif choice == '3':
            break
        else:
            print("Invalid choice.")

def list_wireless_nodes(config):
    print("\n--- Available Wireless Nodes ---")
    nodes = config.get_all_wireless_nodes()
    if not nodes:
        print("No Wireless Nodes found in the configuration.")
        return False
    for i, node in enumerate(nodes):
        print(f"  {i+1}. {node.name}")
    return True

def select_wn_menu(config):
    nodes = config.get_all_wireless_nodes()
    if not nodes:
        print("No Wireless Nodes found to edit.")
        return
    list_wireless_nodes(config)
    try:
        choice = int(input("Enter the number of the Node to edit: "))
        if 0 < choice <= len(nodes):
            selected_node = nodes[choice - 1]
            edit_wn_menu(selected_node)
        else:
            print("Invalid number.")
    except ValueError:
        print("Invalid input. Please enter a number.")

def edit_wn_menu(node):
    while True:
        print(f"\n--- Editing {node.name} ---")
        print("1. View All Parameters")
        print("2. Edit a Parameter")
        print("3. Back to Main Menu")
        choice = input("Enter your choice (1-3): ")
        if choice == '1':
            node.show_all_params()
        elif choice == '2':
            param_name = input("Enter the exact parameter name to edit (e.g., 'IP_ADDRESS'): ")
            param_value = input(f"Enter the new value for '{param_name}': ")
            node.edit_parameter(param_name, param_value)
        elif choice == '3':
            break
        else:
            print("Invalid choice.")

def _get_valid_coordinate(prompt):
    while True:
        val_str = input(prompt)
        try:
            val_float = float(val_str)
            return val_float
        except ValueError:
            print("Invalid input. Please enter a number (e.g., 100.0 or 75.5).")

def create_new_ap(config):
    print("\n--- Create New Access Point ---")
    x = _get_valid_coordinate("Enter X location: ")
    y = _get_valid_coordinate("Enter Y location: ")
    config.create_access_point(x, y)

def create_new_router(config):
    print("\n--- Create New Router ---")
    x = _get_valid_coordinate("Enter X location: ")
    y = _get_valid_coordinate("Enter Y location: ")
    config.create_router(x, y)

def create_new_wn(config):
    print("\n--- Create New Wireless Node ---")
    x = _get_valid_coordinate("Enter X location: ")
    y = _get_valid_coordinate("Enter Y location: ")
    config.create_wireless_node(x, y)

def create_new_wireless_link(config):
    print("\n--- Create New Wireless Link ---")
    aps = config.get_all_access_points()
    if not list_access_points(config):
        return
    try:
        ap_choice = int(input("Enter the number of the AP: "))
        if not (0 < ap_choice <= len(aps)):
            print("Invalid number."); return
        selected_ap = aps[ap_choice - 1]
    except ValueError:
        print("Invalid input. Please enter a number."); return
    print(f"\nNow, select the Wireless Nodes to connect to {selected_ap.name}:")
    nodes = config.get_all_wireless_nodes()
    if not list_wireless_nodes(config):
        return
    node_choices_str = input("Enter node numbers (e.g., '1' or '1, 2, 4'): ")
    selected_nodes = []
    try:
        choice_indices = [int(n.strip()) - 1 for n in node_choices_str.split(',')]
        for idx in choice_indices:
            if 0 <= idx < len(nodes): selected_nodes.append(nodes[idx])
            else: print(f"Warning: Node number {idx+1} is invalid. Skipping.")
        if not selected_nodes:
            print("No valid nodes selected. Aborting link creation."); return
    except ValueError:
        print("Invalid input. Please enter numbers separated by commas."); return
    config.create_wireless_link(selected_ap, selected_nodes)

def create_link_wizard(config):
    """
    Unified link creator:
      1) Wireless (AP ↔ Node(s)) using existing logic
      2) Wired (any two devices) using no-template builder
    """
    print("\n=== Create Link Wizard ===")
    print("1) Wireless (AccessPoint ↔ Node(s))")
    print("2) Wired (any two devices)")
    choice = input("Pick link type (1/2): ").strip()

    if choice == "1":
        aps = config.get_all_access_points()
        if not aps:
            print("No Access Points found."); return
        ap = _pick_from_list("Pick the Access Point:", aps, label=lambda d: d.name, allow_multi=False)
        if not ap: return
        nodes = config.get_all_wireless_nodes()
        if not nodes:
            print("No Nodes found."); return
        chosen_nodes = _pick_from_list(f"Pick one or more Nodes to connect to {ap.name}:", nodes,
                                       label=lambda d: d.name, allow_multi=True)
        if not chosen_nodes: return
        config.create_wireless_link(ap, chosen_nodes)
        return

    if choice == "2":
        devices = config.get_all_devices_wrapped()
        if len(devices) < 2:
            print("Need at least two devices in the config."); return
        a = _pick_from_list("Pick Device A:", devices, label=lambda d: d.name, allow_multi=False)
        if not a: return
        b = _pick_from_list("Pick Device B:", devices, label=lambda d: d.name, allow_multi=False)
        if not b or b is a:
            print("Invalid selection. Device B must be different from A."); return
        print("\n(Optional) Assign IPv4 addresses (press Enter to skip):")
        a_ip =  None
        b_ip =  None
        mask = None
        if a_ip or b_ip:
            mask =  "255.255.255.0"
        link_name =  None
        up =  "100"
        down = "100"
        err_up = "1E-07"
        err_down = "1E-07"
        pdu = "5"
        pdd = "5"
        config.create_wired_link(
            a, b,
            a_ip=a_ip, b_ip=b_ip, mask=mask,
            link_name=link_name,
            link_speed_up=up, link_speed_down=down,
            err_up=err_up, err_down=err_down,
            prop_delay_up=pdu, prop_delay_down=pdd
        )
        return

    print("Invalid choice.")

def wizard_delete_application(config: "NetSimConfig"):
    """
    CLI helper: list applications and let user pick one to delete.
    """
    app_cfg = config._get_application_config_root()
    apps = app_cfg.findall('APPLICATION')
    if not apps:
        print("No applications to delete.")
        return

    print("\n--- Existing Applications ---")
    for i, app in enumerate(apps, 1):
        print(f"  {i}. ID={app.get('ID')}, NAME={app.get('NAME')}, KEY={app.get('KEY')}, TYPE={app.get('APPLICATION_TYPE')}")
    choice = input("Enter the number of the application to delete (or 'id:<ID>' / 'name:<NAME>' ), or 'q' to cancel: ").strip()
    if not choice or choice.lower() == 'q':
        print("Cancelled.")
        return

    # allow direct id:name selections
    if choice.lower().startswith('id:'):
        try:
            aid = int(choice.split(':',1)[1].strip())
            deleted = config.delete_application(app_id=aid)
            if not deleted: print("Delete failed.")
            return
        except ValueError:
            print("Invalid ID provided."); return
    if choice.lower().startswith('name:'):
        nm = choice.split(':',1)[1].strip()
        if not nm:
            print("Invalid name."); return
        deleted = config.delete_application(app_name=nm)
        if not deleted: print("Delete failed.")
        return

    # otherwise interpret as index
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(apps):
            app = apps[idx]
            confirm = input(f"Confirm delete ID={app.get('ID')}, NAME={app.get('NAME')}? (y/N): ").strip().lower()
            if confirm == 'y':
                if config.delete_application(app_id=app.get('ID')):
                    print("Deleted.")
                else:
                    print("Delete failed.")
            else:
                print("Cancelled.")
        else:
            print("Invalid selection.")
    except ValueError:
        print("Invalid input.")



def save_file(config):
    print(f"Saving configuration to '{config.config_file}'...")
    try:
        config.save_config(config.config_file)
    except Exception as e:
        print(f"Error overwriting file: {e}")
        print("Save failed.")


def main_menu(config):
    while True:
        print("\n--- NetSim Python API ---")
        print("1. List all Access Points")
        print("2. Edit an Access Point")
        print("3. List all Routers")
        print("4. Edit a Router")
        print("5. List all Wireless Nodes")
        print("6. Edit a Wireless Node")
        print("7. Create New Access Point")
        print("8. Create New Router")
        print("9. Create New Wireless Node")
        print("10. List all Links")
        print("11. Create New Wireless Link")
        print("12. Save Configuration")
        print("13. Exit")
        print("14. Create Link (Wizard)")
        print("15. Create Application (Unicast CBR)")   # NEW
        print("16. Create Application (Multicast CBR)")
        print("17: Delete Application")


        choice = input("Enter your choice (1-17): ")

        if choice == '1': list_access_points(config)
        elif choice == '2': select_ap_menu(config)
        elif choice == '3': list_routers(config)
        elif choice == '4': select_router_menu(config)
        elif choice == '5': list_wireless_nodes(config)
        elif choice == '6': select_wn_menu(config)
        elif choice == '7': create_new_ap(config)
        elif choice == '8': create_new_router(config)
        elif choice == '9': create_new_wn(config)
        elif choice == '10': list_links(config)
        elif choice == '11': create_new_wireless_link(config)
        elif choice == '12': save_file(config)
        elif choice == '13': print("Exiting..."); break
        elif choice == '14': create_link_wizard(config)

        elif choice == '15': wizard_create_unicast_cbr(config)
        elif choice == '16': wizard_create_multicast_cbr(config)
        elif choice == '17': wizard_delete_application(config)

        else:
            print("Invalid choice, please try again.")


if __name__ == "__main__":
    # Accept path via CLI: python script.py "D:\...\Configuration\Config.netsim"
    config_path = r"D:\NetSim\pls\1\Configuration.netsim"
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        # Try common names relative to script
        candidates = [
            "Config.netsim",
            "Configuration.netsim",
            os.path.join("Configuration", "Config.netsim"),
        ]
        for c in candidates:
            if os.path.exists(c):
                config_path = c
                break

    if not config_path or not os.path.exists(config_path):
        print("Error: Provide path to your NetSim config, e.g.:")
        print(r"D:\NetSim\pls\1\Configuration.netsim")
        sys.exit(1)

    netsim_config = NetSimConfig(config_path)
    main_menu(netsim_config)
