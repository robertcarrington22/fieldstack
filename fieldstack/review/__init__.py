"""
Review layer: the one screen a project executive touches.

The job runner writes a draft package (snapshot, facts, narrative, links) to the
drafts directory. The review server serves an editor over it. Approving renders the
final report from the edited narrative, writes it to the approved directory, and runs
the tenant's deliveries. Nothing reaches the owner without that click.
"""
