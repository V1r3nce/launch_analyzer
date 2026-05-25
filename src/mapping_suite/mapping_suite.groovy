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

        string(name: 'CONFLUENCE_PARENT_PAGE_ID', defaultValue: '', description: 'ID страницы Confluence, тело которой будет перезаписано маппингом')
        text(name: 'SUITE_URLS', defaultValue: '', description: 'URL сьюта(ов) Allure TestOps. Можно передать несколько URL, каждый с новой строки')
    }
    environment{
        ALLURE_URL           = "https://allure.nexign.com"
        ALLURE_TOKEN         = credentials('tech_launch_analyzer')
        CONFLUENCE_URL       = "https://confluence.nexign.com"
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
        stage ('Get Mapping Suite') {
            steps {
                echo '--- Get Mapping Suite ---'
                git branch: 'master', credentialsId: 'mops_ssh', url: "ssh://git@gitlab.nexign.com:2222/products/uds/suite-mapping.git"
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
                            pip install --no-cache-dir --index-url ${PIP_INDEX_URL} -r requirements.txt
                        """
                        if (params.CONFLUENCE_PARENT_PAGE_ID == null || params.CONFLUENCE_PARENT_PAGE_ID.trim().isEmpty()) {
                            currentBuild.result = 'FAILURE'
                            error("CONFLUENCE_PARENT_PAGE_ID is necessary")
                        }
                        def suite_urls = (params.SUITE_URLS ?: "")
                                .split("\\r?\\n")
                                .collect { it.trim() }
                                .findAll { it }
                        if (suite_urls.isEmpty()) {
                            currentBuild.result = 'FAILURE'
                            error("At least one SUITE_URL is necessary")
                        }
                        def suite_lines = suite_urls
                                .collect { "--suite_url '" + it.replace("'", "'\\''") + "'" }
                                .join(' ')

                        def exitCodeCore  = sh (
                            label: "Run core script",
                            returnStatus: true,
                            script: """
export PYTHONPATH=${WORKSPACE}
python ${WORKSPACE}/scripts/confluence/mapping_to_confluence.py \\
    --parent_id ${params.CONFLUENCE_PARENT_PAGE_ID.trim()} \\
    ${suite_lines}
"""
                        )
                        if (exitCodeCore != 0) {
                            currentBuild.result = 'FAILURE'
                            error("mapping_to_confluence.py failed with exit code ${exitCodeCore}")
                        }
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
