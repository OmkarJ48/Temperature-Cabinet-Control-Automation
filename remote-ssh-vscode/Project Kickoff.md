Project Kick-Off: Temperature Cabinet SetpointControl from CODESYS HMI
Project Context
The hydrostatic leak detection automation project has been a useful feasibility exercise. The outcomesuggests that the available options are not currently practical or cost-effective, but the work has helpedus understand the limitations and can be revisited in future if demand increases.
The next project is to investigate and prototype a method of changing the temperature cabinet setpointfrom the CODESYS HMI. This is another useful step towards more automated valve testing and shouldprovide good hands-on experience with CODESYS, HMI development, hardware integration, and safetesting.
Project Objective
Develop a safe and reliable method of allowing an operator to change the setpoint of the selectedtemperature cabinet from a CODESYS HMI.
The system should allow the operator to:
enter a new desired setpoint on the HMI;
send the new setpoint to the cabinet;
confirm, where possible, that the cabinet has accepted the new setpoint;
see a clear warning or fault if the write fails, communication is lost, or the setpoint is notaccepted.
The cabinet should remain responsible for controlling its own temperature. CODESYS should onlyprovide supervisory setpoint control.
Equipment to Use
The agreed equipment for this project is:
Control panel:
DLS008
Temperature cabinet:
Left Hand Small Temperature Cabinet
CODESYS project:
New sandbox project only
This equipment can be used for testing as long as it is not required for R&D work. R&D work takespriority.
Initial CODESYS Setup
OJ should contact TL for guidance on setting up a new CODESYS project and integrating the DLS008control panel hardware.
•
•
•
•
•
•
•
1
This should be treated as a handover rather than just a demonstration. OJ should take clear notes andturn them into a short setup guide that can be used as a reference later.
The guide should cover:
how to create a new CODESYS project;
how to add/configure the required hardware;
required libraries/settings;
how to connect to the PLC safely;
how to download/go online safely;
how to create a basic HMI page;
any common issues or useful screenshots.
Scope
In Scope
Out of Scope for Now
Modifying the R&D CODESYS project.
Full automatic temperature profiling.
Full valve test sequence integration.
Replacing the cabinet’s internal controller.
Writing a custom PID loop in CODESYS.
Multi-cabinet support.
Recipe management.
Purchasing parts without approval.
Hardware and Parts
Not all required hardware may be available at the start. Part of the project is to identify what is neededand suggest suitable options.
Any request for additional parts should include:
Item
Why It Is Needed
Suggested Option
Approx. Cost
Existing available parts should be checked before requesting anything new.
•
•
•
•
•
•
•
•
•
•
•
•
•
•
•
• Creating a new CODESYS sandbox project. - DoneIntegrating the DLS008 hardware into the new project. - Done Investigating how the Left Hand Small Temperature Cabinet can accept a remote setpoint. Identifying any additional hardware, wiring, settings, or documentation required. Creating a basic HMI input for the required setpoint.Sending the requested setpoint from CODESYS to the cabinet. Confirming the setpoint has been accepted, where possible.Adding basic validation and fault indication. Documenting the findings, setup, and test process.
•
•
•
•
•
•
•
•
2
Definition of Done
The first version of the project is complete when:
a new CODESYS project has been created for DLS008;
the required hardware has been configured in the sandbox project;
the method for remotely changing the cabinet setpoint has been identified and documented;
a basic HMI allows a new setpoint to be entered and sent to the cabinet;
invalid setpoints and basic communication/write issues are handled sensibly;
the prototype has been demonstrated on the agreed equipment;
the setup and test process have been documented clearly enough to refer back to later.
Expected Approach
OJ should lead the investigation and propose the route forward. The aim is not to be given every step,but to explore the options, understand the equipment, identify what is needed, and recommend asensible approach.
Support will be available to steer the project, answer questions, and sign off larger actions whereneeded, but ownership of the project should sit with OJ as much as possible.
•
•
•
•
•
•
•
3
