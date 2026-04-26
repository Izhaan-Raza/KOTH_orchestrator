import hudson.security.*
import jenkins.model.*

def instance = Jenkins.getInstance()
instance.disableSecurity()
instance.save()
