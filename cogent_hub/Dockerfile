ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /usr/src

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
