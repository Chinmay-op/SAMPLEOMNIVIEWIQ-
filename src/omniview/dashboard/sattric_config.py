"""
SaTTric+ Configuration UI — Foundation & Navigation (Task 1)
============================================================

This is the UI shell for configuring the SaTTric+ Energy Edge Box.
It implements the basic navigation, draft status display, and the 
initial Device Setup Wizard (Onboarding).
"""

import streamlit as st

def render_device_setup():
    st.header("Device Setup Wizard")
    st.write("First-time onboarding for a new SaTTric+ device.")
    
    with st.form("device_setup_form"):
        site_name = st.text_input("Site Name", placeholder="e.g. Pune Compressor House")
        device_serial = st.text_input("Device Serial Number", placeholder="SAT-XXXX")
        
        st.subheader("Network Settings")
        network_type = st.selectbox("Connection Type", ["Ethernet", "Cellular/SIM"])
        
        if network_type == "Ethernet":
            ip_mode = st.radio("IP Assignment", ["DHCP", "Static"])
            if ip_mode == "Static":
                st.text_input("IP Address")
                st.text_input("Subnet Mask")
                st.text_input("Gateway")
        else:
            st.text_input("APN (Access Point Name)")
            st.text_input("SIM PIN (optional)")
            
        submitted = st.form_submit_button("Save Device Settings")
        if submitted:
            st.session_state["has_draft_changes"] = True
            st.success("Device settings saved to draft!")

def render_meter_setup():
    st.header("Meter Setup")
    st.info("Meter library and setup will be implemented here (Task 2).")

def render_io_setup():
    st.header("Input / Output Channel Mapping")
    st.info("I/O mapping and calibration will be implemented here (Task 3).")

def render_comms_setup():
    st.header("Communication Ports")
    st.info("Advanced port setup will be implemented here.")

def render_rules_setup():
    st.header("Rule Builder")
    st.info("Local automation rules will be implemented here (Task 4).")

def render_review_deploy():
    st.header("Review & Deploy")
    st.info("Review drafted changes and commit them to the device (Task 5).")
    
    if st.button("Publish Changes to Device"):
        st.session_state["has_draft_changes"] = False
        st.success("Configuration successfully deployed to device!")

def main():
    st.set_page_config(page_title="SaTTric+ Config", page_icon="⚙️", layout="wide")
    
    # Initialize session state for draft status
    if "has_draft_changes" not in st.session_state:
        st.session_state["has_draft_changes"] = False

    st.sidebar.title("SaTTric+ Configuration")
    
    # Draft status indicator
    if st.session_state["has_draft_changes"]:
        st.sidebar.warning("⚠️ Draft changes pending. Go to Review & Deploy to publish.")
    else:
        st.sidebar.success("✅ All changes deployed.")

    st.sidebar.markdown("---")
    
    # Navigation
    menu = [
        "Device Setup Wizard",
        "Energy Meter Setup",
        "I/O Channel Mapping",
        "Communication Ports",
        "Rule Builder",
        "Review & Deploy"
    ]
    
    choice = st.sidebar.radio("Navigation", menu)
    
    if choice == "Device Setup Wizard":
        render_device_setup()
    elif choice == "Energy Meter Setup":
        render_meter_setup()
    elif choice == "I/O Channel Mapping":
        render_io_setup()
    elif choice == "Communication Ports":
        render_comms_setup()
    elif choice == "Rule Builder":
        render_rules_setup()
    elif choice == "Review & Deploy":
        render_review_deploy()

if __name__ == "__main__":
    main()
