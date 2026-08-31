from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import log_audit_event
from apps.transactions.models import Transaction

from .models import InvestigationLog
from .orchestrator import ask_investigation_assistant


class AskSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000)


class InvestigationAskView(APIView):
    """
    POST /api/investigate/{transaction_id}/ask/

    Accepts natural-language questions about the selected
    transaction.
    """

    def post(self, request, transaction_id):
        txn = get_object_or_404(
            Transaction,
            transaction_id=transaction_id,
        )

        serializer = AskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        question = serializer.validated_data["question"].strip()

        if not question:
            return Response(
                {
                    "detail": "Please enter a question about the transaction."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = ask_investigation_assistant(
                question,
                default_transaction_id=transaction_id,
            )

            answer = result.get(
                "answer",
                "No investigation answer was generated.",
            )

            tools_called = result.get(
                "tools_called",
                [],
            )

            # -------------------------------------------------
            # IMPORTANT:
            #
            # The orchestrator returns:
            #
            # ["get_investigation_context"]
            #
            # NOT:
            #
            # [{"name": "get_investigation_context"}]
            #
            # The previous code incorrectly used t["name"].
            # -------------------------------------------------

            normalized_tools = []

            for tool in tools_called:
                if isinstance(tool, str):
                    normalized_tools.append(tool)

                elif isinstance(tool, dict):
                    name = tool.get("name")

                    if name:
                        normalized_tools.append(str(name))

            InvestigationLog.objects.create(
                transaction=txn,
                question=question,
                answer=answer,
                tools_called=normalized_tools,
            )

            log_audit_event(
                txn,
                actor="llm_assistant",
                action="investigation_question",
                new_state={
                        "question": question,
                        "tools_called": result.get("tools_called", []),
                    },
            )

            return Response(
                {
                    "transaction_id": transaction_id,
                    "question": question,
                    "answer": answer,
                    "tools_called": normalized_tools,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as exc:

            # Do not expose Django debug HTML to the frontend.
            # Return a proper JSON response instead.
            return Response(
                {
                    "transaction_id": transaction_id,
                    "question": question,
                    "answer": (
                        "The investigation assistant encountered "
                        "an internal error while analyzing this "
                        "transaction."
                    ),
                    "error": str(exc),
                    "tools_called": [],
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )