// == Параметры для настройки под проект ==

def PIP_INDEX_URL="https://artifactory.nexign.com/artifactory/api/pypi/pypi/simple"

def agent_label = '(woi-rhel8 && docker) || woi-tmp-rhel8-docker'

// Идентификатор (ID) credentials для Git в Jenkins
def git_credentials_id = 'mops_ssh'


// == Константы для стиля разделителей в параметрах сборки ==

def separator_section_header_style = """
	background-color: #bff04e;
	text-align: center;
	padding: 4px;
	color: #343434;
    font-size: 22px;
	font-weight: normal;
	text-transform: uppercase;
	font-family: Open Sans, sans-serif;
	letter-spacing: 1px;
	font-style: italic;
"""
def separator_style = "border-width: 0"

pipeline {
    agent {
        label agent_label
    }
    options {
        timestamps ()
    }

    parameters {
        separator(name: "test_parameters", sectionHeader: "Parameters",
                separatorStyle: separator_style, sectionHeaderStyle: separator_section_header_style)

        string(name: 'URL_UDS_launch', defaultValue: '', description: 'URL to launch in UDS space')
        string(name: 'URL_DELIVERY_launch', defaultValue: '', description: 'Optional. URL to launch in DELIVERY_RM space')
        string(name: 'ID_UDS_launch', defaultValue: '', description: 'Alternative to URL_UDS_launch. ID of launch in UDS space')
        string(name: 'ID_DELIVERY_launch', defaultValue: '', description: 'Alternative to URL_DELIVERY_launch. Optional too. ID of launch in DELIVERY_RM space')
        string(name: 'CONFLUENCE_PARENT_PAGE_ID', defaultValue: '809141770', description: 'Default id of confluence page. Result page will be a child of the specified page')
    }
    environment{
        ALLURE_ENDPOINT      = "https://allure.nexign.com"
        ALLURE_TOKEN         = credentials('TESTOPS_TOKEN')
        CONFLUENCE_ENDPOINT  = "https://confluence.nexign.com/"
        CONFLUENCE_PAGE_ID   = "${CONFLUENCE_PARENT_PAGE_ID}"
        CONFLUENCE_USER      = credentials('CONFLUENCE_USER')
        CONFLUENCE_USERNAME  = "${CONFLUENCE_USER_USR}"
        CONFLUENCE_PASSWORD  = "${CONFLUENCE_USER_PSW}"

    }
    stages {
        stage('Set build name') {
            steps {
                script {
                    currentBuild.displayName = "#${BUILD_NUMBER}"
                }
            }
        }
        stage('Clean workspace') {
            steps {
                echo '--- Clean workspace ---'
                cleanWs deleteDirs:true
            }
        }
        stage ('Get Launch Analyzer') {
            steps {
                echo '--- Get UI Tests ---'
                dir("launch-analyzer") {
                    git branch: 'master', credentialsId: 'mops_ssh', url: "ssh://git@gitlab.nexign.com:2222/products/uds/launch_analyzer.git"
                }
            }
        }
        stage("Run script") {
            steps {
                script {
                    docker.image('docker.nexign.com/library/python:3.12-slim').inside(' --privileged'+
                        ' -u root' +
                        ' -e SHELL=/bin/bash' +
                        ' --dns-search=billing.ru' +
                        ' --dns-search=net.billing.ru' +
                        ' -v /var/run/docker.sock:/var/run/docker.sock'+
                        ' -e PYTHONUNBUFFERED=1'
                        ) {
                        sh """
                            cd launch-analyzer
                            pip install --no-cache-dir --index-url ${PIP_INDEX_URL} -r requirements.txt
                        """
                        def uds_line = ""
                        if (params.URL_UDS_launch.isEmpty() && params.ID_UDS_launch.isEmpty()) {
                            currentBuild.result = 'FAILURE'
                            error("One of URL or ID UDS launch is necessary")
                        } else {
                            uds_line = (params.URL_UDS_launch.isEmpty()) ? "--launch_id_uds ${params.ID_UDS_launch}" : "--launch_url_uds ${params.URL_UDS_launch}"
                        }

                        def delivery_line = ""
                        if (params.URL_DELIVERY_launch.isEmpty() || params.ID_DELIVERY_launch.isEmpty()) {
                            delivery_line = (params.URL_DELIVERY_launch.isEmpty()) ? "--launch_id_uds ${params.ID_DELIVERY_launch}" : "--launch_url_uds ${params.URL_DELIVERY_launch}"
                        }
                        def exitCodeCore  = sh (
                            label: "Run core script",
                            returnStatus: true,
                            script: """
                                /bin/bash -c 'set -o pipefail; \
                                cd launch-analyzer && \
                                export PYTHONPATH=$PWD && \
                                python ${WORKSPACE}/scripts/confluence/report_to_confluence.py \
                                ${uds_line} \
                                ${delivery_line}
                            """
                        )
                    }
                }
            }
        }
    }
    post {
        always {
            cleanWs deleteDirs:true
        }
    }
}
