import streamlit as st
from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider
from eth_tester import EthereumTester, PyEVMBackend
from solcx import compile_standard, install_solc
import time

st.set_page_config(page_title="Sim Smart Contract (Streamlit)", layout="centered")

st.title("Simulación de Smart Contract: de contrato en castellano a Solidity")
st.caption("Cadena de pruebas en memoria (EthereumTester). No necesitas wallet.")

# ---------- Texto contractual (castellano) ----------
with st.expander("📜 Contrato en castellano (base didáctica)", expanded=True):
    st.markdown(
        """
**“Contrato básico de compraventa con pago y confirmación de entrega”**

1. **Partes**: Vendedor (A) y Comprador (B).  
2. **Objeto**: Entrega del bien/servicio descrito como “OBJETO”.  
3. **Precio**: “PRECIO” pagadero en un único pago.  
4. **Plazo**: La operación debe completarse antes de la **FECHA LÍMITE**.  
5. **Flujo**:  
   a) Ambas partes **firman** el contrato.  
   b) El Comprador **paga** el precio.  
   c) El Comprador **confirma la entrega**.  
   d) Tras la confirmación, el Vendedor **recibe los fondos**.  
6. **Cancelación**: Si se cancela antes de concluir, se devuelven los fondos al Comprador.
"""
    )

# ---------- Código Solidity embebido ----------
SOLIDITY_SRC = """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract ContratoBasico {
    address public vendedor;
    address public comprador;
    string public objeto;
    uint256 public precioWei;
    uint256 public fechaLimite; // epoch (segundos)

    enum Estado { Borrador, Activo, Resuelto, Cancelado }
    Estado public estado;

    event Firmado(address vendedor, address comprador);
    event Pagado(address from, uint256 amount);
    event EntregaConfirmada(address by);
    event Cancelado(address by, uint256 devolucion);

    modifier soloPartes() {
        require(msg.sender == vendedor || msg.sender == comprador, "Solo partes");
        _;
    }

    constructor(
        address _comprador,
        string memory _objeto,
        uint256 _precioWei,
        uint256 _fechaLimite
    ) {
        vendedor = msg.sender;
        comprador = _comprador;
        objeto = _objeto;
        precioWei = _precioWei;
        fechaLimite = _fechaLimite;
        estado = Estado.Borrador;
    }

    function firmar() external soloPartes {
        require(estado == Estado.Borrador, "No en borrador");
        require(block.timestamp < fechaLimite, "Plazo vencido");
        estado = Estado.Activo;
        emit Firmado(vendedor, comprador);
    }

    function pagar() external payable {
        require(estado == Estado.Activo, "No activo");
        require(msg.sender == comprador, "Solo comprador");
        require(msg.value == precioWei, "Importe incorrecto");
        emit Pagado(msg.sender, msg.value);
    }

    function confirmarEntrega() external {
        require(estado == Estado.Activo, "No activo");
        require(msg.sender == comprador, "Solo comprador");
        estado = Estado.Resuelto;
        (bool ok, ) = vendedor.call{value: address(this).balance}("");
        require(ok, "Fallo pago a vendedor");
        emit EntregaConfirmada(msg.sender);
    }

    function cancelar() external soloPartes {
        require(
            estado == Estado.Activo || estado == Estado.Borrador,
            "No cancelable"
        );
        estado = Estado.Cancelado;
        uint256 saldo = address(this).balance;
        if (saldo > 0) {
            (bool ok, ) = comprador.call{value: saldo}("");
            require(ok, "Fallo devolucion");
        }
        emit Cancelado(msg.sender, saldo);
    }

    function tiempoRestante() external view returns (uint256) {
        if (block.timestamp >= fechaLimite) return 0;
        return fechaLimite - block.timestamp;
    }
}
"""

with st.expander("🧩 Código Solidity (traducción del contrato)", expanded=True):
    st.code(SOLIDITY_SRC, language="solidity")

# ---------- Compilación ----------
with st.status("Instalando/seleccionando compilador Solidity 0.8.24…", expanded=False) as status:
    install_solc("0.8.24")
    status.update(label="Compilando contrato…", state="running")
    compiled = compile_standard(
        {
            "language": "Solidity",
            "sources": {"ContratoBasico.sol": {"content": SOLIDITY_SRC}},
            "settings": {"outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}}}
        },
        solc_version="0.8.24",
    )
    status.update(label="Compilado ✔", state="complete")

abi = compiled["contracts"]["ContratoBasico.sol"]["ContratoBasico"]["abi"]
bytecode = compiled["contracts"]["ContratoBasico.sol"]["ContratoBasico"]["evm"]["bytecode"]["object"]

# ---------- Cadena de pruebas en memoria ----------
backend = PyEVMBackend()
tester = EthereumTester(backend=backend)
w3 = Web3(EthereumTesterProvider(tester))

cuentas = w3.eth.accounts
vendedor = cuentas[0]
comprador = cuentas[1]

st.sidebar.header("Cuentas simuladas")
st.sidebar.write(f"**Vendedor:** `{vendedor}`")
st.sidebar.write(f"**Comprador:** `{comprador}`")
st.sidebar.caption("Ambas con saldo de prueba en esta cadena simulada.")

# ---------- Parámetros ----------
st.subheader("Parámetros del contrato")
col1, col2 = st.columns(2)
with col1:
    objeto = st.text_input("Objeto (texto libre)", value="Portátil X")
    precio_eth = st.number_input("Precio (ETH)", value=0.01, min_value=0.0, step=0.005, format="%.5f")
with col2:
    plazo_min = st.number_input("Plazo (minutos)", value=60, min_value=1, step=5)
    fecha_limite = int(time.time()) + int(plazo_min * 60)

precio_wei = Web3.to_wei(precio_eth, "ether")

# ---------- Despliegue ----------
if "contract_addr" not in st.session_state:
    st.session_state.contract_addr = None

if st.button("🚀 Desplegar contrato (vendedor)"):
    Contrato = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = Contrato.constructor(comprador, objeto, precio_wei, fecha_limite).transact({"from": vendedor})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    st.session_state.contract_addr = receipt.contractAddress
    st.success(f"Contrato desplegado en: {st.session_state.contract_addr}")

if not st.session_state.contract_addr:
    st.info("Despliega el contrato para activar las acciones.")
    st.stop()

contrato = w3.eth.contract(address=st.session_state.contract_addr, abi=abi)

# ---------- Lectura de estado ----------
def leer_estado():
    try:
        est = contrato.functions.estado().call()
        obj = contrato.functions.objeto().call()
        ven = contrato.functions.vendedor().call()
        com = contrato.functions.comprador().call()
        precio = contrato.functions.precioWei().call()
        fecha = contrato.functions.fechaLimite().call()
        try:
            rest = contrato.functions.tiempoRestante().call()
        except:
            rest = 0
        return est, obj, ven, com, precio, fecha, rest
    except Exception as e:
        st.error(f"Error leyendo estado: {e}")
        return None

estados = ["Borrador", "Activo", "Resuelto", "Cancelado"]
datos = leer_estado()
if datos:
    est, obj, ven, com, precio, fecha, rest = datos
    st.markdown("### Estado del contrato")
    st.write(f"- **Estado:** {estados[est]}")
    st.write(f"- **Objeto:** {obj}")
    st.write(f"- **Precio:** {Web3.from_wei(precio, 'ether')} ETH ({precio} wei)")
    st.write(f"- **Vendedor:** `{ven}`")
    st.write(f"- **Comprador:** `{com}`")
    st.write(f"- **Fecha límite (epoch):** {fecha}")
    st.write(f"- **Tiempo restante (s):** {rest}")

st.markdown("---")

# ---------- Acciones ----------
st.subheader("Acciones (máquina de estados)")

c1, c2, c3, c4 = st.columns(4)

with c1:
    if st.button("✍️ Firmar (v/c)"):
        try:
            tx_hash = contrato.functions.firmar().transact({"from": vendedor})
            w3.eth.wait_for_transaction_receipt(tx_hash)
            st.success("Contrato firmado por vendedor.")
        except Exception as e:
            st.error(f"Error (vendedor): {e}")
        try:
            tx_hash = contrato.functions.firmar().transact({"from": comprador})
            w3.eth.wait_for_transaction_receipt(tx_hash)
            st.success("Contrato firmado por comprador.")
        except Exception as e:
            st.warning(f"Info (comprador): {e}")

with c2:
    if st.button("💳 Pagar (comprador)"):
        try:
            tx_hash = contrato.functions.pagar().transact({"from": comprador, "value": precio_wei})
            w3.eth.wait_for_transaction_receipt(tx_hash)
            st.success("Pago realizado por el comprador.")
        except Exception as e:
            st.error(f"Error en pago: {e}")

with c3:
    if st.button("✅ Confirmar entrega (comprador)"):
        try:
            tx_hash = contrato.functions.confirmarEntrega().transact({"from": comprador})
            w3.eth.wait_for_transaction_receipt(tx_hash)
            st.success("Entrega confirmada. Fondos liberados al vendedor.")
        except Exception as e:
            st.error(f"Error al confirmar: {e}")

with c4:
    if st.button("🛑 Cancelar (v/c)"):
        try:
            tx_hash = contrato.functions.cancelar().transact({"from": vendedor})
            w3.eth.wait_for_transaction_receipt(tx_hash)
            st.success("Cancelación solicitada por vendedor (si procede).")
        except Exception as e:
            st.warning(f"Info (vendedor): {e}")
        try:
            tx_hash = contrato.functions.cancelar().transact({"from": comprador})
            w3.eth.wait_for_transaction_receipt(tx_hash)
            st.success("Cancelación solicitada por comprador (si procede).")
        except Exception as e:
            st.warning(f"Info (comprador): {e}")

# ---------- Explicación didáctica ----------
with st.expander("🧠 Mapa mental → formal → código (explicación)", expanded=False):
    st.markdown(
        """
- **Partes (A/B)** → direcciones `address` en la cadena (`vendedor`, `comprador`).
- **Objeto** → `string objeto` (solo describe; no garantiza entrega física).
- **Precio** → `precioWei` (wei); `pagar()` exige importe exacto.
- **Plazo** → `fechaLimite` comparado con `block.timestamp`.
- **Estados** → `enum Estado`: Borrador → Activo → Resuelto/Cancelado.
- **Firmar** → `firmar()` pasa a Activo; exige ser parte y estar en plazo.
- **Pago** → `pagar()` retiene fondos en el contrato (escrow).
- **Confirmación** → `confirmarEntrega()` libera fondos al vendedor.
- **Cancelación** → `cancelar()` reembolsa al comprador si hay saldo.
- **Eventos** → `emit` para auditoría (log on-chain).
- **Garantías** → `require(...)` como condiciones del contrato.
"""
    )

# ---------- Refresco ----------
if st.button("🔄 Refrescar estado"):
    st.rerun()
